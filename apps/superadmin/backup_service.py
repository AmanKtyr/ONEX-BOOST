"""
Enterprise-grade Backup & Disaster Recovery Service for ONEXIVASaaS.
Handles Full Project, Single Gym Tenant, and Media Backups & Restorations.
"""

import os
import io
import sys
import zipfile
import shutil
import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction, connection
from django.core import serializers
from django.core.management import call_command
from django.utils import timezone
from django.contrib.auth.models import User

# Model imports
from apps.superadmin.models import Gym, GymAdmin, SubscriptionPlan, GymSubscription, SystemSetting, BackupLog
from apps.settings.models import PaymentSetting
from apps.members.models import (
    Member, MedicalHistory, EmergencyContact, MembershipHistory,
    PersonalTrainer, MembershipFreeze, AssignDietPlan, AssignWorkoutPlan
)
from apps.trainers.models import Trainer, TrainerSalary
from apps.attendance.models import MemberAttendance, TrainerAttendance, TrainerLeave, MemberLeave
from apps.billing.models import Payment
from apps.expenses.models import Expense
from apps.enquiry.models import Enquiry
from apps.inventory.models import Item, StockLog, Equipment, Maintenance
from apps.management.models import MembershipPlan, DietPlan, WorkoutPlan
from apps.events.models import Event, EventParticipant
from apps.login.models import SubAdmin, SubAdminPermission
from apps.whatsapp.models import WhatsAppConfig, WhatsAppMessageLog


BACKUP_DIR = os.path.join(settings.BASE_DIR, 'backups')


def ensure_backup_dir():
    """Ensure the backups storage directory exists."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def format_file_size(size_bytes):
    """Format bytes into readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_media_stats():
    """Calculate total size and breakdown of the media directory."""
    media_root = settings.MEDIA_ROOT
    total_size = 0
    total_files = 0
    breakdown = {}

    if os.path.exists(media_root):
        for root, dirs, files in os.walk(media_root):
            rel_dir = os.path.relpath(root, media_root)
            top_folder = rel_dir.split(os.sep)[0] if rel_dir != '.' else 'root'
            
            if top_folder not in breakdown:
                breakdown[top_folder] = {'files': 0, 'size': 0, 'size_display': '0 KB'}

            for f in files:
                fp = os.path.join(root, f)
                try:
                    sz = os.path.getsize(fp)
                    total_size += sz
                    total_files += 1
                    breakdown[top_folder]['files'] += 1
                    breakdown[top_folder]['size'] += sz
                except OSError:
                    pass

    for k, v in breakdown.items():
        v['size_display'] = format_file_size(v['size'])

    return {
        'total_size_bytes': total_size,
        'total_size_display': format_file_size(total_size),
        'total_files': total_files,
        'breakdown': breakdown,
    }


def get_system_storage_stats():
    """Returns database size, engine, backup directory size, and media stats."""
    db_engine = settings.DATABASES['default']['ENGINE']
    is_sqlite = 'sqlite' in db_engine.lower()
    db_size_bytes = 0
    db_name = str(settings.DATABASES['default']['NAME'])

    if is_sqlite and os.path.exists(db_name):
        try:
            db_size_bytes = os.path.getsize(db_name)
        except OSError:
            db_size_bytes = 0

    ensure_backup_dir()
    backup_files_count = 0
    backup_total_size = 0
    for f in os.listdir(BACKUP_DIR):
        fp = os.path.join(BACKUP_DIR, f)
        if os.path.isfile(fp):
            backup_files_count += 1
            backup_total_size += os.path.getsize(fp)

    media_stats = get_media_stats()

    return {
        'db_engine': db_engine.split('.')[-1].upper(),
        'db_name': os.path.basename(db_name) if is_sqlite else db_name,
        'db_size_bytes': db_size_bytes,
        'db_size_display': format_file_size(db_size_bytes),
        'is_sqlite': is_sqlite,
        'backup_files_count': backup_files_count,
        'backup_total_size_bytes': backup_total_size,
        'backup_total_size_display': format_file_size(backup_total_size),
        'media_stats': media_stats,
        'gym_count': Gym.objects.count(),
        'member_count': Member.objects.count(),
    }


# ==============================================================================
# 1. SELECTED GYM EXPORT ENGINE
# ==============================================================================

def collect_gym_media_files(gym):
    """Finds all relative media files belonging to a specific Gym."""
    media_root = Path(settings.MEDIA_ROOT)
    collected = set()

    def add_field_file(field_file):
        if field_file and hasattr(field_file, 'name') and field_file.name:
            rel = field_file.name
            full_path = media_root / rel
            if full_path.exists() and full_path.is_file():
                collected.add(rel)

    # Gym fields
    add_field_file(gym.logo)
    add_field_file(gym.qr_code)

    # Gym Admins
    for admin in GymAdmin.objects.filter(gym=gym):
        add_field_file(admin.photo)

    # SubAdmins
    for sub in SubAdmin.objects.filter(gym=gym):
        add_field_file(sub.photo)

    # Trainers
    for trainer in Trainer.objects.filter(gym=gym):
        add_field_file(getattr(trainer, 'photo', None))

    # Members
    for member in Member.objects.filter(gym=gym):
        add_field_file(member.profile_picture)
        add_field_file(member.sign)
        add_field_file(member.identity_document_image)

    # Equipment
    for eq in Equipment.objects.filter(gym=gym):
        add_field_file(eq.image)

    # Event Participants
    for ep in EventParticipant.objects.filter(event__gym=gym):
        add_field_file(ep.payment_screenshot)

    # Payment settings
    try:
        ps = PaymentSetting.objects.filter(gym=gym).first()
        if ps:
            add_field_file(ps.qr_code)
    except Exception:
        pass

    return list(collected)


def export_gym_data_dict(gym):
    """
    Serializes all database entities belonging to a specific gym into
    a clean, self-contained list of records with counts.
    """
    records = []
    counts = {}

    def serialize_qs(qs, model_name):
        nonlocal records, counts
        try:
            if not qs.exists():
                counts[model_name] = 0
                return
            serialized = serializers.serialize('python', qs)
            counts[model_name] = len(serialized)
            records.extend(serialized)
        except Exception as e:
            counts[model_name] = 0

    # 1. Gym
    serialize_qs(Gym.objects.filter(pk=gym.pk), 'gym')

    # 2. Users tied to this gym (Admins, Subadmins, Trainers, Members)
    user_ids = set()
    admin_users = GymAdmin.objects.filter(gym=gym, user__isnull=False).values_list('user_id', flat=True)
    user_ids.update(admin_users)
    subadmin_users = SubAdmin.objects.filter(gym=gym, user__isnull=False).values_list('user_id', flat=True)
    user_ids.update(subadmin_users)
    trainer_users = Trainer.objects.filter(gym=gym, user__isnull=False).values_list('user_id', flat=True)
    user_ids.update(trainer_users)
    member_users = Member.objects.filter(gym=gym, user__isnull=False).values_list('user_id', flat=True)
    user_ids.update(member_users)

    if user_ids:
        serialize_qs(User.objects.filter(pk__in=user_ids), 'user')

    # 3. Gym Admins & Subadmins
    serialize_qs(GymAdmin.objects.filter(gym=gym), 'gym_admin')
    serialize_qs(SubAdmin.objects.filter(gym=gym), 'sub_admin')
    serialize_qs(SubAdminPermission.objects.filter(sub_admin__gym=gym), 'sub_admin_permission')

    # 4. Settings & Subscriptions
    serialize_qs(PaymentSetting.objects.filter(gym=gym), 'payment_setting')
    # Associated subscription plans
    plan_ids = GymSubscription.objects.filter(gym=gym).values_list('subscription_id', flat=True)
    if plan_ids:
        serialize_qs(SubscriptionPlan.objects.filter(pk__in=plan_ids), 'subscription_plan')
    serialize_qs(GymSubscription.objects.filter(gym=gym), 'gym_subscription')

    # 5. Management Plans
    serialize_qs(MembershipPlan.objects.filter(gym=gym), 'membership_plan')
    serialize_qs(DietPlan.objects.filter(gym=gym), 'diet_plan')
    serialize_qs(WorkoutPlan.objects.filter(gym=gym), 'workout_plan')

    # 6. Trainers & Salaries & Leaves & Attendance
    serialize_qs(Trainer.objects.filter(gym=gym), 'trainer')
    serialize_qs(TrainerSalary.objects.filter(trainer__gym=gym), 'trainer_salary')
    serialize_qs(TrainerLeave.objects.filter(trainer__gym=gym), 'trainer_leave')
    serialize_qs(TrainerAttendance.objects.filter(gym=gym), 'trainer_attendance')

    # 7. Members & Sub-profiles
    serialize_qs(Member.objects.filter(gym=gym), 'member')
    serialize_qs(MembershipHistory.objects.filter(member__gym=gym), 'membership_history')
    serialize_qs(MedicalHistory.objects.filter(member__gym=gym), 'medical_history')
    serialize_qs(EmergencyContact.objects.filter(member__gym=gym), 'emergency_contact')
    serialize_qs(PersonalTrainer.objects.filter(gym=gym), 'personal_trainer')
    serialize_qs(MembershipFreeze.objects.filter(membership__member__gym=gym), 'membership_freeze')
    serialize_qs(AssignDietPlan.objects.filter(gym=gym), 'assign_diet_plan')
    serialize_qs(AssignWorkoutPlan.objects.filter(gym=gym), 'assign_workout_plan')
    serialize_qs(MemberAttendance.objects.filter(gym=gym), 'member_attendance')
    serialize_qs(MemberLeave.objects.filter(gym=gym), 'member_leave')

    # 8. Finance & Operations
    serialize_qs(Payment.objects.filter(gym=gym), 'billing_payment')
    serialize_qs(Expense.objects.filter(gym=gym), 'expense')
    serialize_qs(Enquiry.objects.filter(gym=gym), 'enquiry')

    # 9. Inventory
    serialize_qs(Item.objects.filter(gym=gym), 'inventory_item')
    serialize_qs(StockLog.objects.filter(gym=gym), 'stock_log')
    serialize_qs(Equipment.objects.filter(gym=gym), 'equipment')
    serialize_qs(Maintenance.objects.filter(gym=gym), 'equipment_maintenance')

    # 10. Events
    serialize_qs(Event.objects.filter(gym=gym), 'event')
    serialize_qs(EventParticipant.objects.filter(event__gym=gym), 'event_participant')

    # 11. WhatsApp logs & config
    serialize_qs(WhatsAppConfig.objects.filter(gym=gym), 'whatsapp_config')
    serialize_qs(WhatsAppMessageLog.objects.filter(gym=gym), 'whatsapp_log')

    return records, counts


# ==============================================================================
# 2. CREATING BACKUPS
# ==============================================================================

def create_gym_backup(gym, include_media=True, user=None, notes=""):
    """
    Creates an industry-ready .zip archive containing all data and media
    for a single gym.
    """
    ensure_backup_dir()
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    safe_gym_name = "".join(c for c in gym.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"backup_gym_{safe_gym_name}_{gym.gym_id}_{timestamp_str}.zip"
    filepath = os.path.join(BACKUP_DIR, filename)

    records, counts = export_gym_data_dict(gym)
    media_files = collect_gym_media_files(gym) if include_media else []

    manifest = {
        'manifest_version': '1.0',
        'backup_type': 'gym',
        'created_at': timezone.now().isoformat(),
        'gym_id': gym.gym_id,
        'gym_pk': gym.pk,
        'gym_name': gym.name,
        'includes_database': True,
        'includes_media': include_media,
        'record_counts': counts,
        'total_records': len(records),
        'media_files_count': len(media_files),
        'notes': notes,
    }

    media_root = Path(settings.MEDIA_ROOT)
    with zipfile.ZipFile(filepath, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Manifest
        zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))

        # 2. Data json
        # Serializer python format dumped to JSON string
        data_json = json.dumps(records, indent=2, default=str)
        zf.writestr('gym_data.json', data_json)

        # 3. Media files
        if include_media:
            for rel_path in media_files:
                abs_path = media_root / rel_path
                if abs_path.exists() and abs_path.is_file():
                    arcname = f"media/{rel_path}".replace('\\', '/')
                    zf.write(abs_path, arcname=arcname)

    file_size = os.path.getsize(filepath)
    log = BackupLog.objects.create(
        filename=filename,
        file_path=filepath,
        backup_type='gym',
        gym=gym,
        gym_name=gym.name,
        includes_database=True,
        includes_media=include_media,
        file_size_bytes=file_size,
        file_size_display=format_file_size(file_size),
        status='completed',
        notes=notes,
        manifest_data=manifest,
        created_by=user,
    )

    return log, filepath


def create_full_backup(include_db=True, include_media=False, user=None, notes=""):
    """
    Creates an industry-ready full system backup archive containing
    complete database dump, SQLite snapshot (if applicable), and media tree.
    """
    ensure_backup_dir()
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"backup_full_system_{timestamp_str}.zip"
    filepath = os.path.join(BACKUP_DIR, filename)

    is_sqlite = 'sqlite' in settings.DATABASES['default']['ENGINE'].lower()
    sqlite_path = str(settings.DATABASES['default']['NAME'])

    gym_count = Gym.objects.count()
    member_count = Member.objects.count()

    manifest = {
        'manifest_version': '1.0',
        'backup_type': 'full',
        'created_at': timezone.now().isoformat(),
        'gym_count': gym_count,
        'member_count': member_count,
        'includes_database': include_db,
        'includes_media': include_media,
        'db_engine': settings.DATABASES['default']['ENGINE'],
        'notes': notes,
    }

    with zipfile.ZipFile(filepath, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Database Dump
        if include_db:
            out = io.StringIO()
            try:
                call_command(
                    'dumpdata',
                    exclude=['contenttypes', 'auth.permission', 'sessions.session'],
                    natural_foreign=True,
                    natural_primary=True,
                    stdout=out
                )
                zf.writestr('database.json', out.getvalue())
            except Exception as e:
                # Fallback to simple dump
                out = io.StringIO()
                call_command('dumpdata', stdout=out)
                zf.writestr('database.json', out.getvalue())

            # If SQLite, also include live online snapshot
            if is_sqlite and os.path.exists(sqlite_path):
                temp_snap = os.path.join(BACKUP_DIR, f"temp_snap_{timestamp_str}.sqlite3")
                try:
                    src_conn = sqlite3.connect(sqlite_path)
                    dst_conn = sqlite3.connect(temp_snap)
                    with dst_conn:
                        src_conn.backup(dst_conn)
                    dst_conn.close()
                    src_conn.close()
                    zf.write(temp_snap, arcname='database.sqlite3')
                finally:
                    if os.path.exists(temp_snap):
                        try:
                            os.remove(temp_snap)
                        except OSError:
                            pass

        # 3. Media files
        if include_media and os.path.exists(settings.MEDIA_ROOT):
            media_root = settings.MEDIA_ROOT
            media_files_count = 0
            for root, dirs, files in os.walk(media_root):
                for f in files:
                    abs_p = os.path.join(root, f)
                    rel_p = os.path.relpath(abs_p, media_root)
                    arcname = f"media/{rel_p}".replace('\\', '/')
                    zf.write(abs_p, arcname=arcname)
                    media_files_count += 1
            manifest['media_files_count'] = media_files_count

        # Rewriting manifest with final counts
        zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))

    file_size = os.path.getsize(filepath)
    log = BackupLog.objects.create(
        filename=filename,
        file_path=filepath,
        backup_type='full',
        gym=None,
        gym_name="All Gyms & Platform Data",
        includes_database=include_db,
        includes_media=include_media,
        file_size_bytes=file_size,
        file_size_display=format_file_size(file_size),
        status='completed',
        notes=notes,
        manifest_data=manifest,
        created_by=user,
    )

    return log, filepath


def create_media_only_backup(gym=None, user=None, notes=""):
    """
    Creates a .zip archive of media assets only (either all media or single gym).
    """
    ensure_backup_dir()
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    scope_name = f"gym_{gym.gym_id}" if gym else "all_platform"
    filename = f"backup_media_{scope_name}_{timestamp_str}.zip"
    filepath = os.path.join(BACKUP_DIR, filename)

    media_root = Path(settings.MEDIA_ROOT)
    manifest = {
        'manifest_version': '1.0',
        'backup_type': 'media',
        'created_at': timezone.now().isoformat(),
        'gym_id': gym.gym_id if gym else None,
        'gym_name': gym.name if gym else 'All Gyms',
        'includes_database': False,
        'includes_media': True,
        'notes': notes,
    }

    files_count = 0
    with zipfile.ZipFile(filepath, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        if gym:
            media_files = collect_gym_media_files(gym)
            for rel in media_files:
                abs_p = media_root / rel
                if abs_p.exists() and abs_p.is_file():
                    arcname = f"media/{rel}".replace('\\', '/')
                    zf.write(abs_p, arcname=arcname)
                    files_count += 1
        else:
            if os.path.exists(settings.MEDIA_ROOT):
                for root, dirs, files in os.walk(settings.MEDIA_ROOT):
                    for f in files:
                        abs_p = os.path.join(root, f)
                        rel_p = os.path.relpath(abs_p, settings.MEDIA_ROOT)
                        arcname = f"media/{rel_p}".replace('\\', '/')
                        zf.write(abs_p, arcname=arcname)
                        files_count += 1

        manifest['media_files_count'] = files_count
        zf.writestr('manifest.json', json.dumps(manifest, indent=2, default=str))

    file_size = os.path.getsize(filepath)
    log = BackupLog.objects.create(
        filename=filename,
        file_path=filepath,
        backup_type='media',
        gym=gym,
        gym_name=gym.name if gym else "All Gyms Media",
        includes_database=False,
        includes_media=True,
        file_size_bytes=file_size,
        file_size_display=format_file_size(file_size),
        status='completed',
        notes=notes,
        manifest_data=manifest,
        created_by=user,
    )

    return log, filepath


# ==============================================================================
# 3. INSPECTION & SAFETY VERIFICATION
# ==============================================================================

def inspect_backup_file(filepath):
    """
    Inspects an existing or uploaded backup file (.zip, .json, .sqlite3)
    and returns a summary report for pre-restore confirmation.
    """
    if not os.path.exists(filepath):
        return {'is_valid': False, 'error': 'File not found on server.'}

    file_size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    # 1. ZIP Archive
    if ext == '.zip':
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                namelist = zf.namelist()
                manifest = None
                if 'manifest.json' in namelist:
                    try:
                        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
                    except Exception:
                        manifest = None

                has_database_json = 'database.json' in namelist or 'gym_data.json' in namelist
                has_sqlite = 'database.sqlite3' in namelist
                media_files = [n for n in namelist if n.startswith('media/') and not n.endswith('/')]

                backup_type = manifest.get('backup_type', 'unknown') if manifest else 'archive'
                gym_name = manifest.get('gym_name', '') if manifest else ''
                gym_id = manifest.get('gym_id', '') if manifest else ''
                record_counts = manifest.get('record_counts', {}) if manifest else {}

                return {
                    'is_valid': True,
                    'file_type': 'zip',
                    'backup_type': backup_type,
                    'manifest': manifest,
                    'gym_name': gym_name,
                    'gym_id': gym_id,
                    'has_database': has_database_json or has_sqlite,
                    'has_sqlite_snapshot': has_sqlite,
                    'has_media': len(media_files) > 0,
                    'media_files_count': len(media_files),
                    'record_counts': record_counts,
                    'file_size_display': format_file_size(file_size),
                    'created_at': manifest.get('created_at', '') if manifest else '',
                }
        except zipfile.BadZipFile:
            return {'is_valid': False, 'error': 'The uploaded file is not a valid or readable ZIP archive.'}

    # 2. JSON Fixture
    elif ext == '.json':
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0 and 'model' in data[0]:
                return {
                    'is_valid': True,
                    'file_type': 'json',
                    'backup_type': 'json_fixture',
                    'total_records': len(data),
                    'has_database': True,
                    'has_media': False,
                    'file_size_display': format_file_size(file_size),
                    'created_at': '',
                }
            return {'is_valid': False, 'error': 'Invalid JSON fixture format (expected list of models).'}
        except Exception as e:
            return {'is_valid': False, 'error': f'JSON parse error: {str(e)}'}

    # 3. SQLite Database
    elif ext in ('.sqlite3', '.db', '.sqlite'):
        try:
            conn = sqlite3.connect(filepath)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
            table_count = cursor.fetchone()[0]
            conn.close()
            return {
                'is_valid': True,
                'file_type': 'sqlite',
                'backup_type': 'raw_sqlite',
                'table_count': table_count,
                'has_database': True,
                'has_media': False,
                'file_size_display': format_file_size(file_size),
                'created_at': '',
            }
        except Exception as e:
            return {'is_valid': False, 'error': f'SQLite read error: {str(e)}'}

    return {'is_valid': False, 'error': f'Unsupported file extension ({ext}). Allowed: .zip, .json, .sqlite3'}


# ==============================================================================
# 4. RESTORATION & DISASTER RECOVERY ENGINE
# ==============================================================================

def create_pre_restore_safety_snapshot():
    """
    Automatically creates a safety snapshot of the database before any restore.
    """
    ensure_backup_dir()
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    db_engine = settings.DATABASES['default']['ENGINE'].lower()
    
    if 'sqlite' in db_engine:
        db_path = str(settings.DATABASES['default']['NAME'])
        if os.path.exists(db_path):
            safety_file = os.path.join(BACKUP_DIR, f"safety_snapshot_before_restore_{timestamp_str}.sqlite3")
            try:
                src = sqlite3.connect(db_path)
                dst = sqlite3.connect(safety_file)
                with dst:
                    src.backup(dst)
                dst.close()
                src.close()
                return safety_file
            except Exception:
                pass
    return None


def restore_backup(filepath, user=None, target_gym_id=None):
    """
    Executes safe restoration from a backup archive (.zip, .json, or .sqlite3).
    Supports restoring single gym data or full system data.
    """
    inspection = inspect_backup_file(filepath)
    if not inspection.get('is_valid'):
        return False, inspection.get('error', 'Invalid backup file')

    # Step 1: Auto safety snapshot
    safety_snapshot = create_pre_restore_safety_snapshot()

    ext = os.path.splitext(filepath)[1].lower()

    try:
        # ======================================================================
        # RESTORE CASE 1: ZIP ARCHIVE
        # ======================================================================
        if ext == '.zip':
            with zipfile.ZipFile(filepath, 'r') as zf:
                namelist = zf.namelist()
                manifest = inspection.get('manifest') or {}
                backup_type = manifest.get('backup_type', 'unknown')

                # A. SINGLE GYM RESTORE
                if backup_type == 'gym' or 'gym_data.json' in namelist:
                    if 'gym_data.json' not in namelist:
                        return False, "Archive is missing 'gym_data.json'."

                    gym_data_raw = zf.read('gym_data.json').decode('utf-8')
                    gym_records = json.loads(gym_data_raw)

                    # Import within atomic transaction
                    with transaction.atomic():
                        # Unpack / restore models
                        for obj in serializers.deserialize('python', gym_records):
                            # Save model instance
                            obj.save()

                    # Extract media files belonging to this gym
                    media_root = Path(settings.MEDIA_ROOT)
                    for n in namelist:
                        if n.startswith('media/') and not n.endswith('/'):
                            rel_target = n[len('media/'):]
                            dest_path = media_root / rel_target
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(n) as sf, open(dest_path, 'wb') as df:
                                shutil.copyfileobj(sf, df)

                    # Log restore event
                    BackupLog.objects.create(
                        filename=os.path.basename(filepath),
                        file_path=filepath,
                        backup_type='gym',
                        gym_name=manifest.get('gym_name', 'Restored Gym'),
                        includes_database=True,
                        includes_media=inspection.get('has_media', False),
                        file_size_bytes=os.path.getsize(filepath),
                        file_size_display=format_file_size(os.path.getsize(filepath)),
                        status='restored',
                        notes=f"Restored successfully on {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                        manifest_data=manifest,
                        created_by=user,
                    )

                    return True, f"Gym '{manifest.get('gym_name', 'Gym')}' data and media restored successfully!"

                # B. FULL SYSTEM RESTORE
                elif backup_type == 'full' or 'database.json' in namelist or 'database.sqlite3' in namelist:
                    is_sqlite = 'sqlite' in settings.DATABASES['default']['ENGINE'].lower()
                    db_path = str(settings.DATABASES['default']['NAME'])

                    # 1. Restore SQLite binary snapshot if available & engine is sqlite
                    if is_sqlite and 'database.sqlite3' in namelist:
                        temp_extract = os.path.join(BACKUP_DIR, "temp_restore.sqlite3")
                        with open(temp_extract, 'wb') as f:
                            f.write(zf.read('database.sqlite3'))

                        try:
                            # Safely replace via SQLite backup API
                            src = sqlite3.connect(temp_extract)
                            dst = sqlite3.connect(db_path)
                            with dst:
                                src.backup(dst)
                            dst.close()
                            src.close()

                            # Close open Django connections to release cached handles
                            from django.db import connection, connections
                            connection.close()
                            for conn in connections.all():
                                try:
                                    conn.close()
                                except Exception:
                                    pass

                            # Automatically run pending migrations on restored database
                            try:
                                call_command('migrate', interactive=False)
                            except Exception as mig_err:
                                logger.warning(f"Post-restore migrate warning: {mig_err}")
                        finally:
                            if os.path.exists(temp_extract):
                                os.remove(temp_extract)

                    # 2. Or restore from database.json
                    elif 'database.json' in namelist:
                        temp_json = os.path.join(BACKUP_DIR, "temp_restore.json")
                        with open(temp_json, 'wb') as f:
                            f.write(zf.read('database.json'))
                        try:
                            call_command('loaddata', temp_json)
                        finally:
                            if os.path.exists(temp_json):
                                os.remove(temp_json)

                    # 3. Unpack all media files
                    media_root = Path(settings.MEDIA_ROOT)
                    for n in namelist:
                        if n.startswith('media/') and not n.endswith('/'):
                            rel_target = n[len('media/'):]
                            dest_path = media_root / rel_target
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(n) as sf, open(dest_path, 'wb') as df:
                                shutil.copyfileobj(sf, df)

                    # Log restore event
                    BackupLog.objects.create(
                        filename=os.path.basename(filepath),
                        file_path=filepath,
                        backup_type='full',
                        gym_name='All Gyms & Platform Data',
                        includes_database=True,
                        includes_media=inspection.get('has_media', False),
                        file_size_bytes=os.path.getsize(filepath),
                        file_size_display=format_file_size(os.path.getsize(filepath)),
                        status='restored',
                        notes=f"Full system restored on {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                        manifest_data=manifest,
                        created_by=user,
                    )

                    return True, "Full system database and media restored successfully!"

                # C. MEDIA ONLY RESTORE
                elif backup_type == 'media':
                    media_root = Path(settings.MEDIA_ROOT)
                    restored_count = 0
                    for n in namelist:
                        if n.startswith('media/') and not n.endswith('/'):
                            rel_target = n[len('media/'):]
                            dest_path = media_root / rel_target
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(n) as sf, open(dest_path, 'wb') as df:
                                shutil.copyfileobj(sf, df)
                            restored_count += 1

                    return True, f"Media archive restored successfully ({restored_count} files unpacked)!"

        # ======================================================================
        # RESTORE CASE 2: JSON FIXTURE
        # ======================================================================
        elif ext == '.json':
            call_command('loaddata', filepath)
            return True, "JSON fixture restored into database successfully!"

        # ======================================================================
        # RESTORE CASE 3: SQLITE SNAPSHOT
        # ======================================================================
        elif ext in ('.sqlite3', '.db', '.sqlite'):
            is_sqlite = 'sqlite' in settings.DATABASES['default']['ENGINE'].lower()
            if not is_sqlite:
                return False, "Cannot restore SQLite file into a non-SQLite database engine."
            
            db_path = str(settings.DATABASES['default']['NAME'])
            src = sqlite3.connect(filepath)
            dst = sqlite3.connect(db_path)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()

            # Close open Django connections to release cached handles
            from django.db import connection, connections
            connection.close()
            for conn in connections.all():
                try:
                    conn.close()
                except Exception:
                    pass

            # Automatically run pending migrations on restored database
            try:
                call_command('migrate', interactive=False)
            except Exception as mig_err:
                logger.warning(f"Post-restore migrate warning: {mig_err}")

            return True, "SQLite database restored successfully!"

    except Exception as e:
        return False, f"Restoration encountered an error: {str(e)}"

    return False, "Unknown restore specification."


# ==============================================================================
# 5. DISK & LOG SYNCHRONIZATION
# ==============================================================================

def sync_backups_with_disk():
    """
    Scans the `backups/` folder and registers any unlogged backups,
    while removing logs for files that no longer exist on disk.
    """
    ensure_backup_dir()

    # 1. Check existing logs and remove if file missing
    for log in BackupLog.objects.all():
        if not os.path.exists(log.file_path):
            log.delete()

    # 2. Check disk files and add missing logs
    for fname in os.listdir(BACKUP_DIR):
        fpath = os.path.join(BACKUP_DIR, fname)
        if os.path.isfile(fpath) and fname.lower().endswith(('.zip', '.json', '.sqlite3')):
            if not BackupLog.objects.filter(filename=fname).exists():
                inspection = inspect_backup_file(fpath)
                manifest = inspection.get('manifest') or {}
                btype = manifest.get('backup_type') or ('gym' if 'gym' in fname else 'full')
                fsize = os.path.getsize(fpath)

                BackupLog.objects.create(
                    filename=fname,
                    file_path=fpath,
                    backup_type=btype if btype in ['full', 'gym', 'media'] else 'full',
                    gym_name=manifest.get('gym_name', ''),
                    includes_database=inspection.get('has_database', True),
                    includes_media=inspection.get('has_media', False),
                    file_size_bytes=fsize,
                    file_size_display=format_file_size(fsize),
                    status='completed',
                    manifest_data=manifest,
                )
