import catalog from "@config/tool_catalog.json"

// Metadata is not proof that an installation is configured or governed.
export const toolCatalog = catalog.tools
export const setupTools = toolCatalog.filter(tool => tool.setup_ui)
