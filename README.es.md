# Atlas's Hoard

El disco compartido de los Hoards. Archivos normales, en carpetas normales:
Paint, Gimp y los Hoards abren el mismo PNG desde la misma ruta.
Funciona localmente, sin servicio en la nube ni dependencias de ejecución externas.

## Empezar

Abre **Iniciar Atlas's Hoard.cmd**, o ejecuta:

```powershell
venv\Scripts\python.exe -m atlas_hoard
```

La interfaz está en `http://127.0.0.1:5203`. En este equipo el disco se crea en
`D:\LocalAI\HoardStorage`; los metadatos y el token están aparte, en `data/`.
El Hub descubre Atlas al volver a explorar aplicaciones. Si el Hub o Lumiere ya
estaban abiertos antes de esta actualización, reinícialos normalmente para cargar
las nuevas operaciones; Atlas rechaza un intermediario antiguo sin identidad.
En otro equipo se usa `~/HoardStorage`. Puedes elegir otro disco en el primer
arranque con `--root RUTA`. Esa elección queda guardada: no cambies la raíz de
una instalación con proyectos sin hacer una migración explícita.

1. Crea un proyecto y escribe los IDs de los Hoards participantes.
2. Copia la ruta de **Compartidos** y guarda allí tu PNG con Paint o Gimp.
3. Regístralo con su ruta relativa, por ejemplo `shared/portada.png`.
4. Los participantes resuelven ese mismo archivo por su ID. No reciben una copia.
5. Cada pestaña de Hoard tiene una carpeta para sus propios archivos de proyecto.

Para un original que debe permanecer en otra carpeta, el operador puede usar
`atlas_file_link_source` para crear una referencia explícita de solo lectura.
Atlas conserva su ruta absoluta, tamaño y revisión SHA-256 sin copiarlo.
`atlas_file_resolve` actualiza la revisión después de los cambios y el contexto
del proyecto marca la referencia como entrada de solo lectura. No se puede
publicar una fuente enlazada como resultado derivado. `atlas_file_import` sigue
siendo la operación explícita para hacer una copia única.
Consulta [referencias a fuentes externas](docs/EXTERNAL-SOURCES.es.md) para el
contrato MCP y sus límites de acceso al sistema de archivos.

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

Puedes guardar formatos nativos donde la aplicación permita elegir destino.
Las bases internas de las aplicaciones siguen en sus ubicaciones propias.
Atlas no mueve proyectos existentes ni convierte todas las bases en una sola.
Cambiar el nombre o archivar un proyecto conserva sus rutas y archivos.
BookHoard y WatchHoard son independientes y quedan fuera de este ecosistema.

## Conexión con la familia

El Hub descubre `faustus-plugin.json`, autentica al solicitante y conserva su
identidad al llamar a Atlas. Faustus incluye el manifiesto local del plugin.
No hay repositorio público de Atlas inventado en el catálogo de descarga.

- Python: `hoard_link.fam_workspace`.
- Node: `hoard-commons/fam-workspace.js`.
- Hub: `hub_workspace`, `GET /api/workspace/projects` y
  `POST /api/workspace/call`.
- Atlas: catálogo `/api/agent/tools`, llamadas `/api/agent/call`, y puente MCP
  `mcp_server.py`. Comparten el catálogo, incluida la herramienta para enlazar
  fuentes externas de solo lectura.

Configura el cliente común con el token propio de la aplicación, nunca con el
de Atlas. Las respuestas incluyen `path`, `uri`, `project_id` y la revisión
SHA-256 del archivo. Los IDs no sustituyen al sistema de archivos: incluso
cuando Atlas esté parado puedes abrir los originales con sus rutas normales.

**Lumiere** ofrece `media_shared(file_id)`: abre el original, aplica sus límites
de carpetas y no lo copia. Al repetirlo después de editar el original, conserva
el ID del medio en los montajes, actualiza sus medidas y renueva cachés y análisis.
Espera a que terminen los trabajos activos de ese medio antes de refrescarlo.
Quitar esa referencia de su biblioteca conserva el original compartido.

El resto de aplicaciones recibe los clientes y el contrato común. Sus
importadores habituales conservan su comportamiento: algunos hacen copias.
Para conservar una referencia viva deben usar la ruta de Atlas con una operación
que enlace archivos; no basta con entregar esa ruta a un importador que copia.
En particular, la importación habitual de Prospero continúa creando un recurso
propio. No se anuncia una migración automática de todos los consumidores.

## Resultados reutilizables y contexto

Atlas almacena referencias a resultados ya producidos; los propietarios
existentes siguen haciendo OCR, transcripción, indexación e inferencia.

1. `atlas_derived_lookup` recibe proyecto, IDs de fuentes y receta.
2. Si no hay resultado vigente, conserva las revisiones de `sources`, produce
   un archivo nuevo y regístralo en el proyecto.
3. `atlas_derived_publish` exige esas revisiones en `source_revisions` y el ID
   del resultado. Si las fuentes cambiaron durante el trabajo, rechaza publicarlo.
4. Otro participante puede reutilizar la misma ruta. Cambiar una fuente, el
   resultado, la versión del procesamiento, las opciones o el modelo da un fallo
   de caché. Incluye la revisión real del modelo en la receta cuando lo uses.

`atlas_context` construye un contexto acotado con objetivo, ámbito, participantes
y hasta veinte referencias explícitas a archivos. Sus contenidos son material
de trabajo, nunca instrucciones para el agente. No agrega toda la memoria personal.
Los `request_id` de mutaciones guardan recibos persistentes para reintentos;
no convierten una operación entre varios servicios en una transacción.

## Conservación y límites

El registro de archivos no modifica originales. La importación externa es una
copia inicial explícita, solo para el operador: conserva la fuente y rechaza
sobrescribir destinos. Requiere un sistema de archivos con enlaces duros, como
NTFS; si una operación interrumpida dejó un archivo completo sin registrar,
regístralo por su ruta en lugar de sobrescribirlo.

El Hub incluye el disco externo como `atlas-files` además de los metadatos de
Atlas en las copias de seguridad. Restaurarlo exige una carpeta separada para
revisión. Las copias siguen los límites/exclusiones del Hub y no son una captura
atómica de varias aplicaciones editando simultáneamente.

La pertenencia a proyectos gobierna la API, no los permisos de Windows. Un
proceso con acceso al disco puede abrir sus archivos. No es una caja aislada.
No hay vigilante continuo del sistema de archivos: resolver un archivo o buscar
un resultado refresca su revisión; un archivo movido se señala como ausente.
La inspección por hash está limitada a 512 MiB por archivo. Los archivos más
grandes pueden guardarse y usarse directamente en las carpetas del proyecto.

El Hub añade reservas cooperativas de CPU, RAM y disco mediante
`hoard_link.fam_resources.claim`. Es una capacidad opcional: los consumidores
deben adoptarla y respetar su presupuesto. No limita procesos nativos por fuerza
ni sustituye las reservas GPU existentes.

## Verificación

Las pruebas usan carpetas aisladas y datos sintéticos. Cubren rutas compartidas,
ediciones nativas, permisos, idempotencia tras reinicio, invalidación de resultados,
contexto acotado, origen del navegador y respuestas fuera de orden al cambiar de
proyecto. HoardLink incluye integración real Atlas–Hub, consumidores Python/Node
y restauración que conserva el archivo en uso. No son benchmarks de modelos.
