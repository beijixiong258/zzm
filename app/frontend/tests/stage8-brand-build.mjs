// Production-mode build of the owned component fixture, NEVER frontend/dist.
import {build} from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"..");
await build({configFile:false,root,plugins:[react()],build:{outDir:path.resolve(root,"../artifacts/stage8/branding/scratch-build"),emptyOutDir:true,rollupOptions:{input:path.join(root,"tests/stage8-brand.html")}}});
