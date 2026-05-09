export const tauriBridge = {
  isTauri() {
    return false;
  },
  resolveResource(_path: string) {
    throw new Error("Tauri bridge not available in CLI");
  },
};

export async function invokeCommand<T>(_command: string, _args?: Record<string, unknown>): Promise<T> {
  throw new Error("Tauri invokeCommand not available in CLI");
}
