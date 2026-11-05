import type { Directive } from "vue";

// TDesign 会把未声明的属性放在外层容器上；原生表单属性和无障碍名称属性
// 应传给实际的输入框或文本域。
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
