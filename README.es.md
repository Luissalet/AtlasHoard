# Atlas's Hoard

Espacio de trabajo local para casos de investigación. Cada caso reúne fuentes con su fiabilidad, entidades y
relaciones que no pueden existir sin evidencia. La app mantiene una cronología, un mapa, un grafo de relaciones y una
matriz de hipótesis en competencia, y redacta informes en los que cada frase cita una fuente. Está pensada para una
persona y un asistente que trabajan juntos: todo está disponible como API REST para la interfaz incluida y como
herramientas MCP, construidas con el mismo código, de modo que no pueden contradecirse.

## Qué hace

- **Casos**: una pregunta, etiquetas, preguntas abiertas y un panel con lo que requiere atención (relaciones sin
  apoyo, disputadas, hechos posiblemente desactualizados, contradicciones, entidades sin relaciones, hipótesis sin
  valorar).
- **Fuentes**: captura de una URL (se extrae el texto legible y se guarda una copia con su hash), texto pegado,
  archivos locales de texto/HTML/PDF o referencias a documentos de otra app de la familia. Cada fuente lleva grado de
  fiabilidad (A-F) y de credibilidad (1-6), origen, fecha de publicación y búsqueda de texto completo.
- **Entidades**: personas, organizaciones, lugares, eventos, documentos, objetos, dominios y conceptos, con alias,
  atributos (cada uno con su fuente), coordenadas y fechas. Se sugieren posibles duplicados con sus motivos; la
  fusión siempre es explícita y se previsualiza antes.
- **Relaciones**: sujeto, predicado, objeto, fechas de vigencia opcionales y evidencia (una fuente más una cita literal
  o una localización). No se puede crear una relación sin evidencia. Las citas se comprueban contra el texto guardado.
- **Estado derivado**, nunca escrito a mano: `claimed` (un origen), `corroborated` (al menos dos orígenes
  independientes), `confirmed` (marcada por una persona y con al menos dos orígenes independientes), `disputed`
  (marcada por una persona), `unsupported` (todas sus fuentes fueron retiradas) y `retracted` (retirada por una
  persona hasta que se restaure). Un origen es un dominio o una referencia; dos fuentes del mismo origen o con
  contenido idéntico cuentan como una.
- **Cascada de retractación**: retirar una fuente no borra nada. Se recalculan las relaciones, se marcan las derivadas
  de una relación sin apoyo y se listan los atributos e hipótesis afectados.
- **Cronología con `as_of`**: las fechas parciales (`2024`, `2024-03`, `2024-03-05`) se tratan como rangos de días;
  `as_of` muestra lo vigente en una fecha. Un hecho cuya vigencia terminó en el pasado es historia (`ended`,
  «terminado»), no un dato desactualizado; `stale` se reserva para hechos que deberían seguir vigentes pero cuya
  última observación supera `ATLAS_STALE_DAYS`. Se señalan huecos y valores incompatibles de predicados de
  valor único (por ejemplo dos sedes a la vez).
- **Mapa** (Leaflet, teselas de OpenStreetMap) con una capa por tipo de entidad, fuentes detrás de cada capa y
  deslizador temporal. **Grafo** (d3-force) con aristas coloreadas por estado y vecindad por profundidad.
- **Hipótesis en competencia (ACH)**: se valora cada evidencia frente a cada hipótesis (`CC`, `C`, `N`, `I`, `II`,
  `NA`). La puntuación cuenta inconsistencias (I = 1, II = 2); la diagnosticidad indica qué evidencia discrimina y la
  nota de sensibilidad nombra la evidencia de la que depende el orden. La primera hipótesis se describe siempre como
  «menos contradicha hasta ahora», nunca como probada.
- **Enriquecedores**, cada uno reversible entero con `enrichment_undo`: `wikidata` (datos públicos de organizaciones,
  lugares, eventos y figuras públicas), `geocode` (Nominatim), `url_capture` y `family_search` (otras apps de la
  familia). Todo lo que añaden queda como `claimed` y cita su fuente.
- **Informes**: Markdown o JSON con citas `[S12]`, relaciones agrupadas por estado, cronología, tabla ACH y lista de
  fuentes con sus grados. El resumen redactado por un modelo (si hay uno configurado) pasa una comprobación de citas:
  cada frase que afirma un hecho debe citar una fuente que exista en el caso; las frases sin cita se marcan y se
  listan las citas inválidas o retiradas. Sin modelo, el resumen se construye de forma determinista.
- **Historial**: cada cambio guarda quién lo hizo (la interfaz o el asistente), qué cambió y los valores antes y después.

## Uso responsable

- **Personas privadas.** Toda entidad de tipo persona se trata como persona privada salvo que se marque
  `public_figure`. Los enriquecedores nunca se ejecutan sobre una persona privada, `family_search` quita sus nombres y
  alias de las consultas salvo que se indique `include_private`, y los informes las señalan. Marcar a alguien como
  figura pública es un acto deliberado y registrado; hazlo solo con personas de función pública documentada.
- **Redes sociales.** La captura de URLs rechaza los dominios de redes sociales. Si tienes derecho a usar una
  publicación, añade su texto a mano como fuente de texto y pon la dirección como referencia.
- **Direcciones locales.** La captura rechaza direcciones privadas, de bucle local y de enlace local salvo que se
  defina `ATLAS_ALLOW_PRIVATE_URLS=1`. Los archivos locales deben ser texto, Markdown, HTML o PDF y pueden limitarse a
  carpetas con `ATLAS_FILE_ROOTS`.
- **Afirmaciones y certeza.** El estado se deriva de la evidencia. El ACH ordena las hipótesis por lo poco que las
  contradice la evidencia y nunca declara una probada. El texto de un modelo se comprueba en sus citas, no en su
  verdad: lo revisa una persona.
- **Deshacer.** Las ejecuciones de enriquecimiento están marcadas y se pueden deshacer con exactitud; una ejecución
  fallida se deshace sola.
- **Servicios externos.** Solo se consultan los proveedores de datos de la sección Créditos. Los nombres de lugar
  van a Nominatim únicamente con la geocodificación activada (Ajustes, o `ATLAS_GEOCODE=0` para apagarla).

## Instalación

Requisitos: Python 3.11+ (Windows, 3.13) y Node.js 22+ para compilar el cliente.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
npm install
npm run build
python -m atlas_hoard             # http://127.0.0.1:5193
```

El cliente compilado se incluye en `atlas_hoard/static`; `npm` solo hace falta para cambiar la interfaz. Con
`python scripts/dev.py` se arrancan la API y el servidor de desarrollo de Vite a la vez.

Variables: `ATLAS_PORT` o `PORT` (5193; con `PORT_STRICT=1` falla en vez de cambiar de puerto), `ATLAS_DATA_DIR`
(`./data`), `ATLAS_GEOCODE` (`0` la desactiva), `ATLAS_ALLOW_PRIVATE_URLS`, `ATLAS_FILE_ROOTS`, `ATLAS_STALE_DAYS`
(730) y `ATLAS_ALLOWED_HOSTS`.

## MCP

`mcp_server.py` es un puente stdio. Nunca abre la base de datos: lee `data/mcp-token`, obtiene la lista de
herramientas de la app en marcha y reenvía cada llamada; si la app no está en marcha, la arranca. Se registra en
cualquier cliente MCP:

```json
{"mcpServers": {"atlas": {"command": "python", "args": ["/ruta/a/atlas/mcp_server.py"],
  "env": {"ATLAS_URL": "http://127.0.0.1:5193", "ATLAS_TOKEN_FILE": "/ruta/a/atlas/data/mcp-token"}}}}
```

`faustus-plugin.json` describe la misma configuración para el espacio de trabajo Faustus.

### Herramientas

| herramienta | qué hace |
| --- | --- |
| `atlas_status` | salud y recuentos; la sonda del modelo se guarda 60 s y nunca bloquea |
| `case_create`, `case_list`, `case_get`, `case_update` | casos y su panel; borrar con `action=delete` y `confirm=true` |
| `source_add`, `source_get`, `source_retract`, `sources_search` | capturar, leer, retirar o restaurar y buscar fuentes |
| `entity_upsert`, `entity_get`, `entity_search`, `entity_merge`, `duplicates_suggest` | entidades, duplicados y fusiones explícitas |
| `relation_add`, `relation_update`, `relation_retract`, `relation_get` | relaciones con evidencia obligatoria; listado por estado, entidad o `as_of` |
| `timeline`, `map_layers`, `graph` | vista fechada, capas del mapa, grafo de relaciones |
| `hypothesis_add`, `ach_rate`, `ach_matrix` | hipótesis en competencia |
| `enrich`, `enrichment_undo` | enriquecedores y su deshacer |
| `case_report` | informe en Markdown o JSON con citas |
| `history` | historial de cambios |

Los resultados enviados a un asistente se recortan a unos 20 KB con una pista para acotar o paginar.

## Familia

Atlas funciona solo. Cuando las demás apps de la familia están en marcha, `family_search` consulta la biblioteca de
Borges (`library_search`) y Links (`search_links`) a través del hub o directamente, y guarda cada resultado como
fuente `family_ref` (`hoard://<app>/<tipo>/<id>` con un extracto corto); si una app no responde, se omite. Los nombres
de las herramientas se configuran en Ajustes. Atlas emite `atlas.case.created`, `atlas.relation.added`,
`atlas.relation.status_changed` y `atlas.source.retracted`, y sus casos se direccionan como `hoard://atlas/case/<id>`.

## Desarrollo

```bash
pip install -r requirements.txt
python -m pytest -q      # sin red: la captura, Wikidata, la geocodificación, el modelo y otras apps se simulan
npm run build
```

La interfaz está en castellano por defecto y en inglés cuando el navegador está en inglés.

## Límites

- Wikidata se lee por su API web (búsqueda y datos de entidad), no por SPARQL.
- La comprobación de direcciones se hace antes de la petición; un servidor que cambie su respuesta DNS entre la
  comprobación y la petición no se detecta.
- La extracción de PDF es solo de texto; los PDF escaneados necesitan OCR aparte.
- Las relaciones con la misma tripleta y fechas distintas se mantienen separadas a propósito; fusiónalas a mano si
  describen el mismo hecho.
- El mapa necesita internet para sus teselas.

## Créditos

Datos de mapa © colaboradores de OpenStreetMap (ODbL); teselas de openstreetmap.org; búsqueda de lugares con
Nominatim; datos de entidades de Wikidata (CC0). Leaflet y d3-force dibujan el mapa y el grafo.

## Licencia

Véase `LICENSE`.
