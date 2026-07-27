"""
Middleware personalizado para agregar headers HTTP de política de permisos.

El header Permissions-Policy le indica al navegador que este sitio tiene
permiso de usar el micrófono. Sin él, Chrome en móvil y Safari en iOS
pueden bloquear silenciosamente el acceso al micrófono (y por ende a
SpeechRecognition) aunque el usuario lo haya autorizado previamente.
"""


class PermissionsPolicyMiddleware:
    """
    Agrega el header `Permissions-Policy: microphone=*` a todas las respuestas.
    Esto es necesario para que el reconocimiento de voz (Web Speech API) funcione
    correctamente en dispositivos móviles y en navegadores modernos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Permite el micrófono para el origen propio (self) y cualquier iframe embebido.
        # 'microphone=*' es la forma más permisiva; si solo quieres tu propio origen
        # usa 'microphone=(self)' en su lugar.
        response['Permissions-Policy'] = 'microphone=*'
        return response
