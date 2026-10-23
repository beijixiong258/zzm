<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../../i18n";
import type { Diagram } from "../../classroom-api";
const props = defineProps<{ modelValue: Diagram; readonly?: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: Diagram] }>();
const svg = ref<SVGSVGElement>();
const selected = ref(""),
  from = ref(""),
  to = ref(""),
  label = ref("");
const markerId = `arrow-${crypto.randomUUID()}`;
const width = computed(() =>
  Math.max(640, ...props.modelValue.nodes.map((n) => n.x + 220)),
);
const height = computed(() =>
  Math.max(220, ...props.modelValue.nodes.map((n) => n.y + 100)),
);
const current = computed(() =>
  props.modelValue.nodes.find((n) => n.id === selected.value),
);
let moving = "";
function update(edit: (value: Diagram) => void) {
  const value = JSON.parse(JSON.stringify(props.modelValue)) as Diagram;
  edit(value);
  emit("update:modelValue", value);
}
function addNode() {
  const id = crypto.randomUUID();
  update((v) =>
    v.nodes.push({
      id,
      text: t("New idea"),
      x: 30 + (v.nodes.length % 3) * 210,
      y: 30 + Math.floor(v.nodes.length / 3) * 110,
    }),
  );
  selected.value = id;
}
function addEdge() {
  if (from.value && to.value && from.value !== to.value) {
    update((v) =>
      v.edges.push({ from: from.value, to: to.value, label: label.value }),
    );
    label.value = "";
  }
}
function removeNode() {
  update((v) => {
    v.nodes = v.nodes.filter((n) => n.id !== selected.value);
    v.edges = v.edges.filter(
      (e) => e.from !== selected.value && e.to !== selected.value,
    );
  });
  selected.value = "";
}
function start(event: PointerEvent, id: string) {
  if (props.readonly) return;
  moving = id;
  selected.value = id;
  (event.currentTarget as Element).setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if (!moving || !svg.value) return;
  const matrix = svg.value.getScreenCTM();
  if (!matrix) return;
  const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(
    matrix.inverse(),
  );
  update((v) => {
    const n = v.nodes.find((n) => n.id === moving);
    if (n) {
      n.x = Math.round(Math.min(3800, Math.max(0, p.x - 90)));
      n.y = Math.round(Math.min(3900, Math.max(0, p.y - 35)));
    }
  });
}
function node(id: string) {
  return props.modelValue.nodes.find((n) => n.id === id);
}
</script>
<template>
  <section class="diagram-editor">
    <div class="row spread">
      <h3 v-if="readonly">{{ modelValue.title }}</h3>
      <input
        v-else
        :value="modelValue.title"
        :aria-label="t('Diagram title')"
        maxlength="200"
        @input="
          update((v) => (v.title = ($event.target as HTMLInputElement).value))
        "
      />
    </div>
    <svg
      ref="svg"
      :viewBox="`0 0 ${width} ${height}`"
      role="img"
      :aria-label="modelValue.title"
      style="background: #ffffff; touch-action: none"
      @pointermove="move"
      @pointerup="moving = ''"
      @pointercancel="moving = ''"
    >
      <defs>
        <marker
          :id="markerId"
          markerWidth="10"
          markerHeight="10"
          refX="9"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L0,6 L9,3 z" fill="#346b60" />
        </marker>
      </defs>
      <g v-for="(edge, index) in modelValue.edges" :key="index">
        <template v-if="node(edge.from) && node(edge.to)">
          <line
            :x1="node(edge.from)!.x + 90"
            :y1="node(edge.from)!.y + 70"
            :x2="node(edge.to)!.x + 90"
            :y2="node(edge.to)!.y"
            stroke="#346b60"
            stroke-width="2"
            :marker-end="`url(#${markerId})`"
          />
          <text
            :x="(node(edge.from)!.x + node(edge.to)!.x) / 2 + 96"
            :y="(node(edge.from)!.y + node(edge.to)!.y) / 2 + 35"
            fill="#244b43"
            font-size="13"
            font-family="sans-serif"
          >
            {{ edge.label }}
          </text>
        </template>
      </g>
      <g
        v-for="n in modelValue.nodes"
        :key="n.id"
        @pointerdown="start($event, n.id)"
        :style="{ cursor: readonly ? 'default' : 'move' }"
      >
        <rect
          :x="n.x"
          :y="n.y"
          width="180"
          height="70"
          rx="10"
          fill="#edf5f1"
          :stroke="selected === n.id && !readonly ? '#ae7024' : '#346b60'"
          stroke-width="2"
        />
        <text
          :x="n.x + 90"
          :y="n.y + 28"
          text-anchor="middle"
          fill="#173f35"
          font-size="14"
          font-family="sans-serif"
        >
          <tspan
            v-for="(line, i) in n.text.split('\n')"
            :key="i"
            :x="n.x + 90"
            :dy="i ? 18 : 0"
          >
            {{ line }}
          </tspan>
        </text>
      </g>
    </svg>
    <div v-if="!readonly" class="form-stack">
      <p class="muted">
        {{
          t(
            "Drag nodes to arrange the diagram. Select a node to edit its text.",
          )
        }}
      </p>
      <div class="row">
        <button
          type="button"
          :disabled="modelValue.nodes.length >= 80"
          @click="addNode"
        >
          {{ t("Add node") }}</button
        ><button v-if="current" type="button" @click="removeNode">
          {{ t("Remove node") }}
        </button>
      </div>
      <textarea
        v-if="current"
        :value="current.text"
        maxlength="500"
        :aria-label="t('Node text')"
        @input="
          update((v) => {
            const n = v.nodes.find((item) => item.id === selected);
            if (n) n.text = ($event.target as HTMLTextAreaElement).value;
          })
        "
      />
      <div class="form-grid">
        <label
          >{{ t("From node")
          }}<select v-model="from">
            <option value="">—</option>
            <option v-for="n in modelValue.nodes" :key="n.id" :value="n.id">
              {{ n.text }}
            </option>
          </select></label
        ><label
          >{{ t("To node")
          }}<select v-model="to">
            <option value="">—</option>
            <option v-for="n in modelValue.nodes" :key="n.id" :value="n.id">
              {{ n.text }}
            </option>
          </select></label
        >
      </div>
      <input
        v-model="label"
        :placeholder="t('Connection label (optional)')"
        maxlength="200"
      /><button
        type="button"
        :disabled="
          !from || !to || from === to || modelValue.edges.length >= 160
        "
        @click="addEdge"
      >
        {{ t("Connect nodes") }}
      </button>
      <div v-for="(edge, i) in modelValue.edges" :key="i" class="row spread">
        <span
          >{{ node(edge.from)?.text }} → {{ node(edge.to)?.text }}
          {{ edge.label }}</span
        ><button type="button" @click="update((v) => v.edges.splice(i, 1))">
          {{ t("Remove") }}
        </button>
      </div>
    </div>
  </section>
</template>
