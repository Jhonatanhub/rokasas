from django.shortcuts import render
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


@login_required
def redireccion_inicio(request):
    user = request.user

    if user.is_superuser:
        return redirect("admin:index")

    if user.groups.filter(name="admin_roka").exists():
        return redirect("form_clientes")

    if user.groups.filter(name="reportador_roka").exists():
        return redirect("form_servicios")

    raise PermissionDenied("El usuario no pertenece a ningún grupo autorizado.")