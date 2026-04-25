

def response_details_from_exception(e: Exception) -> str:
    response = getattr(e, 'response', None)
    if response is None:
        return str(e)
    return f'{response.status_code} {response.text}'
