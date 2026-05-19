"""
Delegator workflow DSL.

YAML is the source of truth for a workflow definition. The canvas designer is
a generator and viewer on top; the runtime never reads anything other than
the parsed YAML.

Public API:
    from app.dsl import load_workflow_yaml, yaml_to_graph, Workflow

    wf = load_workflow_yaml(yaml_text)        # Pydantic model, fully validated
    graph = yaml_to_graph(wf)                 # {"nodes": [...], "edges": [...]}
                                              # — same shape the executor consumes today

The internal graph format is intentionally preserved so ``executor.py`` does
not need to change: YAML is layered *over* the existing runtime, not bolted
into it.
"""
from app.dsl.schema import (  # noqa: F401
    Workflow,
    Block,
    WorkflowParam,
    RunsOn,
    OutputConfig,
    SUPPORTED_BLOCK_TYPES,
    WorkflowValidationError,
)
from app.dsl.loader import (  # noqa: F401
    graph_to_workflow,
    load_workflow_yaml,
    workflow_to_yaml,
    yaml_to_graph,
)
from app.dsl.naming import (  # noqa: F401
    slugify_workflow_name,
    yaml_filename_for,
)
