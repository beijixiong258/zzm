import { createApp } from "vue";
import App from "./App.vue";
import controlAttrs from "./controlAttrs";
import "tdesign-vue-next/es/style/index.css";
import "./design-tokens.css";
import "./classroom.css";

createApp(App).directive("control-attrs", controlAttrs).mount("#root");
