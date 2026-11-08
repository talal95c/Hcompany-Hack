import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";
import {viteSingleFile} from "vite-plugin-singlefile";
export default defineConfig(({mode})=>({
  base:"./",
  plugins:[react(), ...(mode==="single"?[viteSingleFile()]:[])],
  build:mode==="single"?{outDir:"out/single",assetsInlineLimit:Infinity}:undefined,
}));
