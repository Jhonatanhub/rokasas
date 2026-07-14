from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied

def usuarios_en_grupos(nombres_grupos):
    """
    Decorador para verificar si un usuario pertenece a uno o más grupos específicos.
    Si no pertenece, lanza un error 403 (Prohibido).
    """
    def check_user(user):
        if user.is_superuser:
            return True
        
        # Verifica si el usuario está en la lista de grupos permitidos
        if user.groups.filter(name__in=nombres_grupos).exists():
            return True
            
        raise PermissionDenied # Esto enviará al usuario a una página de error 403
        
    return user_passes_test(check_user)