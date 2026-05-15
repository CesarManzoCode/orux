"""Roster: quién está conectado y dónde está trabajando cada quien.

Esto es a la capa 2 lo que `Workspace` es a la capa 1: el estado autoritativo
que el servidor mantiene y desde el cual decide qué mandarle a cada cliente.
La diferencia clave es el ciclo de vida. El estado de un archivo (`Document`)
es persistente: vive mientras viva el workspace. El estado de presencia es
efímero: existe mientras la persona esté conectada y desaparece cuando se va.
Por eso vive en su propia clase y no se mete dentro de `Workspace`.

Decisiones de esta capa:

- **La identidad la asigna el servidor, no el cliente.** El cliente no elige su
  `client_id` ni su nombre: si pudiera, podría hacerse pasar por otro. El
  servidor lleva un contador y reparte identidades anónimas ("anónimo-3") con
  un color de una paleta fija. Cuando llegue la capa de autenticación, este es
  el único lugar donde "anónimo-N" se reemplaza por el nombre real; el resto
  del sistema ya habla en términos de `PresenceState`.

- **Estar conectado no es estar presente.** Un cliente recién conectado que
  todavía no abrió ningún archivo tiene `path = None`: está en la sala pero no
  en ninguna parte del código. No se difunde ni aparece en el roster de nadie
  hasta que abre un archivo. Esto mantiene el tráfico y la UI limpios, y es
  semánticamente correcto: presencia es *dónde trabajas*, no *que existes*.
"""

from __future__ import annotations

from ..protocol import PresenceState

# Paleta fija. Los colores se reparten ciclando: el cliente N usa el color
# N % len(PALETA). Con pocos usuarios (el público objetivo son equipos de 2 a
# 50) las colisiones de color son improbables y, si pasan, no rompen nada:
# son una ayuda visual, no un identificador. El identificador es client_id.
PALETA = ["#e0607a", "#5fa8e0", "#8de0a8", "#e0c46a", "#b98de0", "#e09a5f"]


class Roster:
    def __init__(self) -> None:
        # client_id -> PresenceState. EFÍMERO: es "quién está y dónde *ahora*".
        # Se crea al conectar y se borra al desconectar (la presencia no
        # sobrevive a cerrar la pestaña: si no estás, no estás "aquí").
        self._estados: dict[str, PresenceState] = {}
        # Contador monotónico para repartir client_id. Nunca se reinicia ni
        # reutiliza: ids viejos confundirían a clientes que aún los tienen
        # pintados.
        self._contador = 0
        # IDENTIDAD ESTABLE (mínimo viable, sin auth real). El cliente guarda
        # un token aleatorio en localStorage y lo manda al conectar. Aquí
        # mapeamos token -> client_id, y client_id -> (id, name, color) para
        # poder reconstruir la MISMA identidad cuando recarga la página. Sin
        # esto, cada reload daba un client_id nuevo y se perdía el ownership.
        # Ambos diccionarios son persistentes mientras viva el server (la
        # identidad NO se borra al desconectar, solo la presencia).
        self._por_token: dict[str, str] = {}
        self._identidades: dict[str, dict] = {}

    def asignar(self, token: str | None = None) -> PresenceState:
        """Da identidad a una conexión y le crea su presencia (sin archivo).

        Con `token`: si ya se vio ese token, se REUSA su identidad (mismo
        client_id/nombre/color) — así recargar la página no pierde el
        ownership, que se indexa por client_id. Sin token (o token nuevo): se
        asigna identidad fresca. La presencia siempre nace limpia (`path=None`):
        reconectar no te devuelve a donde estabas, eso es estado efímero.
        """
        if token is not None and token in self._por_token:
            ident = self._identidades[self._por_token[token]]
        else:
            self._contador += 1
            n = self._contador
            ident = {
                "client_id": str(n),
                "name": f"anónimo-{n}",
                "color": PALETA[(n - 1) % len(PALETA)],
            }
            self._identidades[ident["client_id"]] = ident
            if token is not None:
                self._por_token[token] = ident["client_id"]

        estado = PresenceState(**ident)  # path=None, line=1 por defecto
        self._estados[ident["client_id"]] = estado
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
