def registration_credentials_context(request):
    """
    Exposes and clears registration credentials flash data from session for SweetAlert popup.
    """
    if hasattr(request, 'session') and 'registration_credentials' in request.session:
        creds = request.session.pop('registration_credentials')
        return {'registration_credentials': creds}
    return {}
