import os
import django
import requests
import json
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'GYM.settings')
django.setup()



def verify_phone_number():
    """
    Complete phone number verification with Meta
    This is what you need to run to finish the setup
    """
    print(" WhatsApp Phone Number Verification")
    print("=" * 60)
    
    # Your credentials
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    certificate = settings.WHATSAPP_VERIFICATION_CERTIFICATE.strip()
    
    print(f"Phone Number ID: {phone_number_id}")
    print(f"Certificate length: {len(certificate)} characters")
    
    # Step 1: Get current status
    print("\n1. Checking current verification status...")
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            print("✅ Account exists")
            print(f"   Display Name: {data.get('verified_name', 'N/A')}")
            print(f"   Quality Rating: {data.get('quality_rating', 'N/A')}")
            print(f"   Status: {data.get('status', 'N/A')}")
        else:
            print(f"❌ Error: {data}")
            return
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error checking status: {e}")
        return
    
    # Step 2: Submit certificate for verification
    print("\n2. Submitting certificate for verification...")
    
    # The certificate needs to be in the specific format Meta expects
    # For Cloud API, we need to make a POST request to verify the phone number
    
    
    # For Cloud API, the verification might be automatic once webhook is verified
    # Let's check if we need to verify via API
    print("\n3. For Cloud API, verification usually happens automatically")
    print("   when you complete these steps:")
    print("\n   📝 MANUAL STEPS REQUIRED:")
    print("   1. Go to: https://business.facebook.com")
    print("   2. Settings → Accounts → WhatsApp Accounts")
    print("   3. Find your phone number (+916392178640)")
    print("   4. Click on it")
    print("   5. Look for 'Verification' or 'Complete Setup'")
    print("   6. You might need to:")
    print("      a. Upload the certificate file")
    print("      b. Or paste the certificate text")
    print("      c. Or verify via email/SMS")
    
    # Alternative: Try to trigger verification via API if available
    print("\n4. Trying alternative verification methods...")
    
    # Method A: Check if there's a verification endpoint
    methods_url = f"https://graph.facebook.com/v20.0/{phone_number_id}/verification_methods"
    try:
        methods_response = requests.get(methods_url, headers=headers, timeout=10)
        methods_data = methods_response.json()
        print(f"   Verification methods: {json.dumps(methods_data, indent=2)}")
    except requests.exceptions.RequestException:
        print("   Could not fetch verification methods")
    
    print("\n" + "=" * 60)
    print("🎯 NEXT ACTIONS:")
    print("1. Log into https://business.facebook.com")
    print("2. Go to WhatsApp Accounts section")
    print("3. Complete phone verification")
    print("4. Wait up to 24 hours")
    print("5. Status will change from 'Pending' to 'Connected'")
    print("=" * 60)

def check_verification_status():
    """Check verification status periodically"""
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    print("\n🔄 Checking verification status...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            status = data.get('status', 'unknown')
            verified_name = data.get('verified_name', 'Not verified')
            
            print(f"📱 Phone: {data.get('display_phone_number', 'N/A')}")
            print(f"✅ Name: {verified_name}")
            print(f"📊 Status: {status}")
            
            if status == 'CONNECTED':
                print("\n🎉 CONGRATULATIONS! Your WhatsApp Business account is fully verified!")
                print("You can now send messages to customers.")
            elif status == 'PENDING':
                print("\n⏳ Still pending. Please complete the verification steps mentioned above.")
            else:
                print(f"\n❓ Status '{status}' - Check Meta Business Suite for details")
                
        else:
            print(f"❌ Error: {data}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_phone_number()
    check_verification_status()