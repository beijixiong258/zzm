import { ref, watch } from "vue";

export function useTaskTime(boundaries: () => (string | null | undefined)[]) {
  const time = ref(Date.now());
  watch(
    boundaries,
    (values, _previous, onCleanup) => {
      const times = values.map((value) => Date.parse(value || ""));
      let timer: ReturnType<typeof setTimeout>;
      function updateTime() {
        const now = Date.now();
        time.value = now;
        const next = times.reduce(
          (earliest, value) =>
            value > now ? Math.min(earliest, value) : earliest,
          Infinity,
        );
        if (Number.isFinite(next)) {
          timer = setTimeout(updateTime, Math.min(next - now, 2_147_483_647));
        }
      }
      updateTime();
      onCleanup(() => clearTimeout(timer));
    },
    { immediate: true, flush: "sync" },
  );
  return time;
}
