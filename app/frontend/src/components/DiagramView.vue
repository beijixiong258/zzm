<script setup lang="ts">
import { computed } from "vue";
import type { Diagram } from "../classroom-api";

const props = defineProps<{ diagram: Diagram }>();
const markerId = "arrow-" + crypto.randomUUID();
const width = computed(() =>
  Math.max(640, ...props.diagram.nodes.map((node) => node.x + 220)),
);
const height = computed(() =>
  Math.max(220, ...props.diagram.nodes.map((node) => node.y + 100)),
);
const edges = computed(() =>
  props.diagram.edges.map((edge) => ({
    label: edge.label,
    from: props.diagram.nodes.find((node) => node.id === edge.from)!,
    to: props.diagram.nodes.find((node) => node.id === edge.to)!,
  })),
);
</script>

<template>
  <section class="diagram-view">
    <h3>{{ diagram.title }}</h3>
    <svg
      :viewBox="'0 0 ' + width + ' ' + height"
      role="img"
      :aria-label="diagram.title"
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
      <g v-for="(edge, index) in edges" :key="index">
        <line
          :x1="edge.from.x + 90"
          :y1="edge.from.y + 70"
          :x2="edge.to.x + 90"
          :y2="edge.to.y"
          stroke="#346b60"
          stroke-width="2"
          :marker-end="'url(#' + markerId + ')'"
        />
        <text
          :x="(edge.from.x + edge.to.x) / 2 + 96"
          :y="(edge.from.y + edge.to.y) / 2 + 35"
          fill="#244b43"
          font-size="13"
          font-family="sans-serif"
        >
          {{ edge.label }}
        </text>
      </g>
      <g v-for="node in diagram.nodes" :key="node.id">
        <rect
          :x="node.x"
          :y="node.y"
          width="180"
          height="70"
          rx="10"
          fill="#edf5f1"
          stroke="#346b60"
          stroke-width="2"
        />
        <text
          :x="node.x + 90"
          :y="node.y + 28"
          text-anchor="middle"
          fill="#173f35"
          font-size="14"
          font-family="sans-serif"
        >
          <tspan
            v-for="(line, index) in node.text.split('\n')"
            :key="index"
            :x="node.x + 90"
            :dy="index ? 18 : 0"
          >
            {{ line }}
          </tspan>
        </text>
      </g>
    </svg>
  </section>
</template>
