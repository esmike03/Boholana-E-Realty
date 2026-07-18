"""Small shared helper for consistent pagination across list views."""
from django.core.paginator import Paginator


def paginate(request, queryset, per_page=10):
    """Return (page_obj, querystring).

    querystring holds the current GET params minus `page`, so templates can
    build page links that preserve active filters:
        ?{{ querystring }}&page=2
    """
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    return page_obj, querystring
