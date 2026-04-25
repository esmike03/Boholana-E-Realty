# apps/accounts/context_processors.py

def unread_chat_count(request):
    if request.user.is_authenticated and request.user.role in [
        'broker', 'admin', 'staff', 'sale_assistant', 'property_owner'
    ]:
        from apps.reservations.models import ChatMessage
        count = ChatMessage.objects.filter(
            receiver=request.user,
            is_read=False
        ).count()
        return {'total_unread_chat': count}
    return {'total_unread_chat': 0}