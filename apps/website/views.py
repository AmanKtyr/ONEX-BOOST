import logging

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.views.decorators.http import require_GET, require_POST

from .forms import WebsiteContactSubmissionForm
from .models import WebsiteContactSubmission

logger = logging.getLogger(__name__)


def render_public_page(request, template_name, context=None, *, content_type=None, status=200):
    return render(
        request,
        template_name,
        context or {},
        content_type=content_type,
        status=status,
    )


@require_GET
def website_index(request):
    return render_public_page(request, 'website/index.html')


@require_GET
def terms_of_service(request):
    return render_public_page(request, 'website/terms_of_service.html')


@require_GET
def privacy_policy(request):
    return render_public_page(request, 'website/privacy_policy.html')


@require_GET
def refund_policy(request):
    return render_public_page(request, 'website/refund_policy.html')


@require_GET
def sitemap(request):
    return render_public_page(
        request,
        'website/sitemap.xml',
        content_type='application/xml',
    )


@require_GET
def blogs(request):
    return render_public_page(request, 'website/blogs.html')


@require_GET
def blog_detail(request, blog_id):
    template_name = f'website/blogs/blog{blog_id}.html'
    try:
        return render_public_page(request, template_name, {'blog_id': blog_id})
    except TemplateDoesNotExist as exc:
        raise Http404('Blog not found.') from exc


@require_GET
def gym_software_lucknow(request):
    return render_public_page(request, 'website/blogs/blog2.html', {'blog_id': 2})


@require_GET
def how_to_start_gym(request):
    return render_public_page(request, 'website/blogs/blog3.html', {'blog_id': 3})


@require_GET
def bmi_calculator(request):
    return render_public_page(request, 'website/bmi_calculator.html')


@require_GET
def about(request):
    return render_public_page(request, 'website/about.html')


@require_GET
def features(request):
    return render_public_page(request, 'website/features.html')


@require_GET
def contact(request):
    return render_public_page(request, 'website/contact.html')


@require_GET
def pricing(request):
    return render_public_page(request, 'website/pricing.html')


@require_POST
def contact_submission(request):
    form = WebsiteContactSubmissionForm(request.POST)

    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0] if form.errors else 'Please review the form and try again.'
        return JsonResponse(
            {
                'success': False,
                'message': str(first_error),
                'errors': form.errors.get_json_data(),
            },
            status=400,
        )

    try:
        submission = form.save()
    except Exception:
        logger.exception(
            'Failed to save website contact submission for %s',
            request.POST.get('email', ''),
        )
        return JsonResponse(
            {
                'success': False,
                'message': 'We could not submit your request right now. Please try again shortly.',
            },
            status=500,
        )

    logger.info(
        'Website contact submission received from %s %s (%s)',
        submission.first_name,
        submission.last_name,
        submission.email,
    )
    return JsonResponse(
        {
            'success': True,
            'message': 'Message sent successfully!',
        }
    )