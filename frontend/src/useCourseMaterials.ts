import { onBeforeUnmount, ref } from "vue";
import { call, key, type Material } from "./classroom-api";

export function useCourseMaterials(courseId: () => string) {
  const materials = ref<Material[]>([]);
  const error = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  let sequence = 0;
  let disposed = false;

  function schedule(delay: number) {
    timer = setTimeout(() => void load(), delay);
  }

  async function load() {
    clearTimeout(timer);
    const current = ++sequence;
    try {
      const result = await call<Material[]>(
        `/courses/${key(courseId())}/materials`,
      );
      // Upload completion can start another refresh before this one finishes.
      if (disposed || current !== sequence) return false;
      materials.value = result;
      error.value = "";
      if (
        result.some(
          (material) =>
            !material.archived &&
            ["queued", "processing"].includes(material.status),
        )
      ) {
        schedule(2500);
      }
      return true;
    } catch (e) {
      if (disposed || current !== sequence) return false;
      error.value = (e as Error).message;
      schedule(5000);
      return false;
    }
  }

  onBeforeUnmount(() => {
    disposed = true;
    clearTimeout(timer);
  });
  return { materials, error, load };
}
