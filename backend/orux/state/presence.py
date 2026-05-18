"""Roster: quién está conectado y dónde está trabajando cada quien.

Esto es a la capa 2 lo que `Workspace` es a la capa 1: el estado autoritativo
que el servidor mantiene y desde el cual decide qué mandarle a cada cliente.
La diferencia clave es el ciclo de vida. El estado de un archivo (`Document`)
es persistente: vive mientras viva el workspace. El estado de presencia es
efímero: existe mientras la persona esté conectada y desaparece cuando se va.
Por eso vive en su propia clase y no se mete dentro de `Workspace`.

Decisiones de esta capa:

- **La identidad es el usuario autenticado (capa 7).** Ya no hay anónimos ni
  contadores ni tokens: el server solo llama `asignar(usuario)` después de que
  el usuario pasó el login, y la identidad (client_id/nombre/color) se deriva
  determinísticamente de su nombre. El cliente nunca elige su identidad.

- **Estar conectado no es estar presente.** Un cliente recién conectado que
  todavía no abrió ningún archivo tiene `path = None`: está en la sala pero no
  en ninguna parte del código. No se difunde ni aparece en el roster de nadie
  hasta que abre un archivo. Esto mantiene el tráfico y la UI limpios, y es
  semánticamente correcto: presencia es *dónde trabajas*, no *que existes*.
"""

from __future__ import annotations

from hashlib import sha256

from ..protocol import PresenceState

# Paleta fija. El color de un usuario se deriva de su nombre con un hash, así
# es estable entre sesiones y dispositivos (mismo usuario, mismo color) sin
# guardar nada. Si dos usuarios colisionan de color no pasa nada: es ayuda
# visual, el identificador real es el usuario.
PALETA = ["#e0607a", "#5fa8e0", "#8de0a8", "#e0c46a", "#b98de0", "#e09a5f"]


def color_de(username: str) -> str:
    """Color estable y determinista para un usuario."""
    h = int(sha256(username.encode("utf-8")).hexdigest(), 16)
    return PALETA[h % len(PALETA)]


class Roster:
    def __init__(self) -> None:
        # client_id -> PresenceState. EFÍMERO: es "quién está y dónde *ahora*".
        # Se crea al autenticar y se borra al desconectar (la presencia no
        # sobrevive a cerrar la pestaña: si no estás, no estás "aquí").
        #
        # Capa 7: `client_id` ES el usuario real (normalizado). La identidad
        # ya no es un token anónimo con tablas auxiliares: es determinista a
        # partir del usuario (nombre = usuario, color = hash del usuario), así
        # que reconectar desde otro navegador o tras reiniciar el server
        # devuelve exactamente la misma identidad sin guardar mapeos.
        self._estados: dict[str, PresenceState] = {}

    def asignar(self, username: str) -> PresenceState:
        """Crea la presencia (sin archivo) para un usuario ya autenticado.

        La identidad se deriva del usuario, no se inventa: mismo usuario =
        mismo client_id/nombre/color, siempre. La presencia nace limpia
        (`path=None`): reconectar no te devuelve a donde estabas, eso es
        estado efímero.
        """
        estado = PresenceState(
            client_id=username,
            name=username,
            color=color_de(username),
        )
        self._estados[username] = estado
        return estado

    def presentes(self, excepto: str | None = None) -> list[PresenceState]:
        """Quiénes están presentes (ya abrieron un archivo), opcionalmente sin uno.

        `excepto` sirve para armar el `peers` del WelcomeMessage: a ti no te
        mando tu propia presencia en la lista de los demás. Filtramos los que
        tienen `path is None` porque están conectados pero no presentes.
        """
        return [
            e
            for cid, e in self._estados.items()
            if e.path is not None and cid != excepto
        ]

    def lineas_ocupadas(self, path: str, excepto: str) -> set[int]:
        """Qué líneas de `path` tiene ocupadas algún OTRO presente.

        Es la base del lock de la capa 5: "esta línea ya la está tocando
        alguien". Excluimos a `excepto` (el propio editor) — nadie se bloquea
        a sí mismo. Una línea cuenta como ocupada por el simple hecho de que
        otro presente tiene ahí su cursor: presencia = dónde trabaja la gente,
        y trabajar en una línea es reservarla mientras estés ahí.
        """
        return {
            e.line
            for cid, e in self._estados.items()
            if e.path == path and cid != excepto
        }

    def mover(self, client_id: str, path: str, line: int) -> PresenceState | None:
        """Actualiza dónde está un cliente. Devuelve el estado nuevo ya completo.

        El servidor recibe del cliente solo `path` y `line`; este método los
        fusiona con la identidad que el servidor ya tenía guardada para ese
        `client_id`. Así el estado que se difunde lleva nombre y color
        confiables sin que el cliente pueda falsificarlos.

        Devuelve `None` si el `client_id` no existe (conexión que ya cayó):
        el servidor entonces no difunde nada.
        """
        previo = self._estados.get(client_id)
        if previo is None:
            return None
        actualizado = PresenceState(
            client_id=previo.client_id,
            name=previo.name,
            color=previo.color,
            path=path,
            line=line,
        )
        self._estados[client_id] = actualizado
        return actualizado

    def quitar(self, client_id: str) -> PresenceState | None:
        """Saca a un cliente del roster (se desconectó). Devuelve su último estado.

        El servidor usa el valor de retorno para decidir si avisar a los demás:
        si la persona nunca llegó a abrir un archivo (`path is None`) nadie la
        tenía pintada, así que no hace falta mandar un LeaveMessage por ella.
        """
        return self._estados.pop(client_id, None)
