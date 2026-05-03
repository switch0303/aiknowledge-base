import type { Plugin, PluginInput, Hooks } from "@opencode-ai/plugin";

const server: Plugin = async (input: PluginInput): Promise<Hooks> => {
  return {
    "tool.execute.after": async (toolInput) => {
      if (toolInput.tool !== "write" && toolInput.tool !== "edit") {
        return;
      }

      const filePath = toolInput.args.file_path ?? toolInput.args.filePath;
      if (!filePath || typeof filePath !== "string") {
        return;
      }

      if (!filePath.includes("knowledge/articles/") || !filePath.endsWith(".json")) {
        return;
      }

      try {
        const result = await input.$`python3 hooks/validate_json.py ${filePath}`.nothrow();

        if (result.exitCode !== 0) {
          console.error(`[validate-json] Validation failed for ${filePath}`);
          console.error(result.stderr || result.stdout);
        }
      } catch (error) {
        console.error(`[validate-json] Failed to run validator: ${error}`);
      }
    },
  };
};

export { server };
export default server;
