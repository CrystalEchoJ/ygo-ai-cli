export interface LuaConstantItem {
  name: string;
  value: string;
  description: string;
  category: string;
}

export interface LuaFunctionItem {
  name: string;
  namespace: string;
  shortName: string;
  signature: string;
  returnType: string;
  parameters: string[];
  description: string;
  raw: string;
  category?: string;
}

export interface LuaSnippetItem {
  name: string;
  prefix: string;
  body: string[];
  description: string;
  sortText: string;
}

export interface LuaCatalog {
  constants: LuaConstantItem[];
  functions: LuaFunctionItem[];
  snippets: LuaSnippetItem[];
  keywords: string[];
}
