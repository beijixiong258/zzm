import type { Directive } from "vue";

// TDesign places undeclared attributes on its wrapper. Keep native form and
// accessible-name attributes on the actual input or textarea.
type ControlAttributes = Record<string, string | number | boolean | undefined>;
const apply: Directive<HTMLElement, ControlAttributes> = {
  mounted: update,
  updated: update,
};
function update(element: HTMLElement, { value }: { value: ControlAttributes }) {
  const input = element.querySelector("input, textarea");
  if (!input) return;
  for (const [name, attribute] of Object.entries(value)) {
    if (attribute === false || attribute == null) input.removeAttribute(name);
    else input.setAttribute(name, attribute === true ? "" : String(attribute));
  }
}
export default apply;
