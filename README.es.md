# Atlas's Hoard

Almacenamiento compartido local para la familia Hoard: carpetas de proyecto normales que contienen archivos vivos compartidos y los archivos nativos de cada aplicación.

[Read in English](README.md)

## Qué es

Atlas's Hoard da a los proyectos un lugar común en disco. Todas las aplicaciones miembro de un proyecto resuelven la misma ruta original por el ID del archivo, de modo que registrar un PNG nunca lo copia ni lo edita, y los originales siguen abriéndose con sus rutas normales aunque Atlas esté parado. Los metadatos (proyectos, IDs de archivo, revisiones, anclas, resultados derivados) viven aparte, en `data/`. La pertenencia a un proyecto gobierna la API, no los permisos de Windows: un proceso con acceso al disco puede abrir los archivos; Atlas no es una caja aislada.

```text
HoardStorage/
  coleccion-de-otono-<id>/
    shared/
      portada.png
      referencias.pdf
    hoards/
      writer/
      lumiere/
      prospero/
```

Las bases de datos internas de las aplicaciones siguen donde estaban; Atlas no mueve nada ni las unifica. No hay vigilante continuo de archivos ni dependencia de la nube; BookHoard y WatchHoard son independientes.

## Qué hace

**Proyectos**
- Crea un proyecto con nombre, objetivo opcional, esfera y los IDs de los Hoards participantes; cada uno recibe su carpeta junto a `shared/`.
- **Editar proyecto**: cambia nombre, objetivo, participantes y estado activo/archivado; solo se envían los campos cambiados, los borradores sobreviven al cerrar y al refrescar, y renombrar o archivar conserva rutas, IDs de archivo y revisiones. Quitar un Hoard conserva sus carpetas y archivos.
- Un buscador en la barra lateral filtra proyectos por nombre y objetivo (todas las palabras, sin distinguir mayúsculas ni acentos), estado y esfera, sin perder los formularios abiertos.

**Archivos**
- **Register file** toma una ruta relativa como `shared/portada.png` y un título descriptivo opcional; registrar una ruta ya existente conserva su ID y refresca la revisión. Cada archivo tiene un ID, una URI `hoard://atlas/file/<id>`, una revisión SHA-256 y un tamaño.
- **Ver detalles** muestra el ID registrado, la URI, la ruta, la aplicación, la revisión y el tamaño; **Copiar referencia** copia la URI; **Actualizar metadatos** lee el original y refresca los metadatos registrados (un archivo ausente conserva su última revisión registrada, indicada como tal). La inspección por hash se limita a 512 MiB por archivo; los archivos mayores pueden seguir usándose en las carpetas del proyecto.
- Búsqueda de archivos registrados por título o ruta (todas las palabras, sin distinguir mayúsculas ni acentos), por carpeta compartida o nativa y por presencia. Busca en los metadatos registrados, no en el contenido de los archivos ni en carpetas sin registrar.
- **Referencias a fuentes externas** (**Añadir referencia externa**): un archivo que debe quedarse en otra carpeta se enlaza como solo lectura; Atlas conserva su ruta absoluta, tamaño y SHA-256 sin copiarlo. **Comprobar** refresca la revisión, **Copiar ruta original** copia la ruta. Las fuentes enlazadas pueden ser entradas de resultados derivados pero nunca salidas. `atlas_file_import` es la copia única explícita para el operador (nunca sobrescribe y necesita un sistema de archivos con enlaces duros). Véase [docs/EXTERNAL-SOURCES.es.md](docs/EXTERNAL-SOURCES.es.md).

**Resultados reutilizables**
- Atlas guarda referencias a resultados ya producidos; las aplicaciones propietarias siguen haciendo el OCR, la transcripción, la indexación y la inferencia. La vista **Resultados reutilizables** muestra las salidas guardadas, las revisiones de las fuentes y la receta completa, y **Comprobar ahora** contrasta con los hashes actuales de los archivos.
- La consulta recibe proyecto, IDs de fuentes y receta; un acierto de caché exige hashes exactos de fuentes y salida, versión de la operación, opciones y revisión del modelo. Publicar una salida registrada declara que se produjo a partir de esas revisiones de fuente y se rechaza si las fuentes cambiaron entretanto. Atlas no ejecuta la operación.

**Anclas multimodales**
- Marca un lugar exacto de la revisión de un archivo registrado: rango de texto, celdas, página y rectángulo de un PDF, región de imagen, intervalo de audio o vídeo, pieza 3D (GLB/OBJ/STL) o símbolo de código, con comentarios.
- Cuando se registra o refresca una revisión nueva, Atlas vuelve a localizar cada ancla y la anota como intacta, movida, cambiada o perdida en esa revisión; las anclas y sus comentarios siguen fijados a la revisión en la que se hicieron. La pestaña **Anclas / Anchors** del proyecto las lista por archivo y revisión y crea anclas de texto, celdas, PDF y otras desde campos de formulario. Las posiciones de texto en PDF necesitan el paquete opcional `pypdf`. Véase [docs/ANCHORS.es.md](docs/ANCHORS.es.md).

**Contexto**
- `atlas_context` construye un contexto acotado con objetivo, ámbito, participantes y hasta veinte referencias explícitas a archivos. El contenido de los archivos es material de trabajo, nunca instrucciones para el agente.

**Copias de seguridad y recursos.** El Hub incluye el disco externo como `atlas-files` además de los metadatos de Atlas en las copias; restaurar exige una carpeta separada para revisión, y las copias no son una captura atómica de varias aplicaciones editando a la vez. El Hub ofrece además reservas cooperativas de CPU, RAM y disco (`hoard_link.fam_resources.claim`) que los consumidores deben adoptar y respetar.

## Cómo arrancarlo

Abre **Iniciar Atlas's Hoard.cmd**, o ejecuta:

```powershell
python -m atlas_hoard
```

Requiere Python 3.11+ y nada fuera de la biblioteca estándar. La interfaz está en `http://127.0.0.1:5203`. `--root RUTA` elige el disco compartido en el primer arranque (por defecto: `HoardStorage` en la carpeta de desarrollo en Windows si existe, o en la carpeta personal en caso contrario). Esa elección queda guardada; no cambies la raíz de una instalación con proyectos sin una migración explícita.

1. Crea un proyecto y escribe los IDs de los Hoards participantes.
2. Copia la ruta de **Compartidos** y guarda allí tu archivo con cualquier editor.
3. Regístralo por su ruta relativa, por ejemplo `shared/portada.png`.
4. Los participantes resuelven el mismo archivo por su ID; nadie recibe una copia.

## Conexión con Faustus y el Hub

El Hub descubre `faustus-plugin.json`, autentica al solicitante y conserva su identidad al llamar a Atlas. Clientes: Python `hoard_link.fam_workspace`, Node `hoard-commons/fam-workspace.js`, Hub `hub_workspace`, `GET /api/workspace/projects` y `POST /api/workspace/call`. Atlas sirve su catálogo en `/api/agent/tools`, las llamadas en `/api/agent/call` y un puente MCP por stdio, `mcp_server.py`. Las respuestas incluyen `path`, `uri`, `project_id` y la revisión SHA-256.

Herramientas, por grupos:
- Proyectos: `atlas_projects` (con `query`, `state` y `sphere` opcionales), `atlas_project`, `atlas_project_create`, `atlas_project_update` (fusiona solo los campos que recibe), `atlas_location`, `atlas_session`, `atlas_context`.
- Archivos: `atlas_file_register`, `atlas_file_resolve`, `atlas_files_search`, `atlas_file_link_source`, `atlas_file_import`.
- Resultados derivados: `atlas_derived_lookup`, `atlas_derived_publish`, `atlas_derived_results`.
- Anclas: `atlas_anchor_create`, `atlas_anchor_get`, `atlas_anchor_list`, `atlas_anchor_resolve`, `atlas_anchor_comment`.

Las mutaciones llevan un `request_id` que guarda un recibo persistente para los reintentos; esto no convierte una operación entre varios servicios en una transacción.

**Lumiere** ofrece `media_shared(file_id)`: abre el original dentro de los límites de sus carpetas sin copiarlo, y al repetirlo tras editar el original conserva el ID del medio en los montajes, actualiza sus medidas y renueva cachés y análisis. Quitar esa referencia de su biblioteca conserva el original compartido. El resto de aplicaciones recibe los clientes y el contrato comunes; sus importadores habituales conservan su comportamiento y algunos copian archivos, así que una referencia viva requiere una operación que enlace archivos.

**Asistente de Faustus.** El lanzador compartido de Hoard Link muestra el panel de Faustus de la familia (un botón flotante). La conversación, el modelo y las herramientas viven en Faustus; esta app solo le dice al panel qué hay abierto.
- Contexto por vista: un proyecto abierto se envía como `project` (id, nombre, esfera, propietario, objetivo, estado, miembros, ruta, ruta compartida) y los archivos del área actual como `file`, hasta 50 (título, ruta relativa, app, revisión, estado, presencia, ruta). Solo se envían metadatos, nunca el contenido de los archivos.
- Los campos sin guardar (`project_create`, `file_register`) se devuelven con el evento de ventana `atlas:context-request`. Cuando el asistente termina un turno, el proyecto abierto se recarga en el sitio, conservando el texto, el foco y el cursor de lo que se está escribiendo.
- El relevo se monta bajo `/api/copilot/*` (exige sesión o token, salvo el script del lanzador) y el script de la página se sirve en `/copilot-context.js`. La política de seguridad de contenido se mantiene estricta.

**Skills.** La app lleva `shared-project-files`, `revision-aware-media` y `verification-loop` de la biblioteca de skills de la familia para los agentes que se conectan, que se leen con `skills_list` y `skill_read` y se asignan en la página de skills (`/api/agent/skills/page`) o en la pestaña Skills del hub.

## Estructura del proyecto

| Ruta | Contenido |
|---|---|
| `atlas_hoard/` | servidor, almacén, anclas, contratos |
| `atlas_hoard/ui/` | interfaz web |
| `atlas_hoard/hoard_link/` | biblioteca de la familia incluida (conserva su licencia y atribución) |
| `mcp_server.py` | puente MCP por stdio |
| `faustus-plugin.json` | manifiesto del plugin |
| `docs/` | anclas y referencias a fuentes externas (en español e inglés) |
| `tests/` | pruebas de Python y JS |
| `data/` | metadatos y token (no versionados) |

## Pruebas

```powershell
python -m pytest tests
node --test tests/copilot-context.test.mjs tests/anchors-ui.test.mjs tests/external-references.test.mjs
```

Las pruebas usan carpetas aisladas y datos sintéticos.

## Licencia

MIT.
