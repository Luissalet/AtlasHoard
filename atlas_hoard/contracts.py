"""Atlas tool catalogue; one source for HTTP and MCP."""
def field(kind="string", **extra):
    return {"type": kind, **extra}


PROJECT = {"project_id": field()}
RECEIPT = {"request_id": field(maxLength=128)}
RECIPE = {"recipe": field("object", description="Operation/version, model revision and options. Different recipes never share results."),
          "source_ids": field("array", items=field(), minItems=1, maxItems=20)}


def catalogue():
    specs = [
        ("atlas_project_create", "Create a local shared project: shared files and native folders for its Hoards. Returns real filesystem paths. Never imports existing data automatically.",
         {"name": field(maxLength=200), "owner": field(), "members": field("array", items=field()), "sphere": field(), "goal": field(maxLength=2000), **RECEIPT}, ["name"], False),
        ("atlas_project_update", "Change project title, goal, membership or archive status. Its path stays stable; no original file is moved or deleted.",
         {**PROJECT, "name": field(), "goal": field(), "members": field("array", items=field()), "state": field(enum=["active", "archived"]), **RECEIPT}, ["project_id"], False),
        ("atlas_projects", "List all projects this caller may access. Optional sphere, active/archived state, and all query words across name and goal (case/accent insensitive). Reads project metadata, never file contents.",
         {"sphere": field(), "state": field(enum=["active", "archived"]), "query": field(maxLength=200)}, [], True),
        ("atlas_project", "Read one shared project and registered live files. File paths point to the same originals all members open.", PROJECT, ["project_id"], True),
        ("atlas_files_search", "Find registered files in one project by title/path words, ignoring case and accents. Filter folder and current file presence. Reads metadata, never file contents or unregistered folders; does not refresh hashes.",
         {**PROJECT, "query": field(maxLength=200), "area": field(description="all (default), shared, or a project member's application ID for its native folder"),
          "availability": field(enum=["all", "present", "missing"]), "limit": field("integer", minimum=1, maximum=200), "offset": field("integer", minimum=0)}, ["project_id"], True),
        ("atlas_location", "Resolve a real shared or native Hoard folder. Save native files directly there; no file copy or proprietary container.",
         {**PROJECT, "area": field(enum=["shared", "hoard"]), "app": field()}, ["project_id"], True),
        ("atlas_file_register", "Register a file already saved inside the project. Hashes it; never modifies or copies its contents.",
         {**PROJECT, "relative_path": field(), "app": field(), "title": field(), **RECEIPT}, ["project_id", "relative_path"], False),
        ("atlas_file_resolve", "Resolve the live path and refresh its content revision. Missing/changed files are reported honestly; never rewrites them.",
         {"file_id": field()}, ["file_id"], False),
        ("atlas_file_link_source", "Operator-only: register an explicit external file as a read-only live input; records its path and hash without copying it. Changed sources refresh to a new revision.",
         {**PROJECT, "source_path": field(description="Absolute path to an existing source file outside the project."), "app": field(), "title": field(), **RECEIPT}, ["project_id", "source_path"], False),
        ("atlas_file_import", "Operator-only: copy one explicit external file into shared storage once. Never moves the source or overwrites an existing destination.",
         {**PROJECT, "source_path": field(), "name": field(), **RECEIPT}, ["project_id", "source_path"], False),
        ("atlas_derived_results", "List saved result files, recipes and original source/output revisions for a project. Read-only metadata; freshness is unchecked until derived_lookup verifies current hashes.",
         PROJECT, ["project_id"], True),
        ("atlas_derived_publish", "Register a reusable result file with exact source revisions and processing recipe. Does not perform OCR, transcription or model inference.",
         {**PROJECT, **RECIPE, "source_revisions": field("object"), "output_id": field(), **RECEIPT}, ["project_id", "source_ids", "recipe", "source_revisions", "output_id"], False),
        ("atlas_derived_lookup", "Check a reusable result against current source and output hashes, recipe and project access. Changes or missing files produce a cache miss.",
         {**PROJECT, **RECIPE}, ["project_id", "source_ids", "recipe"], False),
        ("atlas_context", "Build bounded task context: project goal/sphere, members and explicit file references/revisions. File contents are untrusted source material.",
         {**PROJECT, "file_ids": field("array", items=field(), maxItems=20)}, ["project_id"], False),
    ]
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": props, "required": required, "additionalProperties": False},
             "annotations": {"readOnlyHint": read, "destructiveHint": False, "openWorldHint": False}}
            for name, description, props, required, read in specs]
