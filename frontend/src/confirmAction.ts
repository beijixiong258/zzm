import { DialogPlugin } from "tdesign-vue-next";
import { t } from "./i18n";

export function confirmAction(
  message: string,
  options: { header?: string; confirmLabel?: string; danger?: boolean } = {},
): Promise<boolean> {
  const trigger = document.activeElement as HTMLElement | null;
  return new Promise((resolve) => {
    const dialog = DialogPlugin.confirm({
      header: options.header || t("Confirm"),
      body: message,
      confirmBtn: options.danger
        ? { content: options.confirmLabel || t("Confirm"), theme: "danger" }
        : options.confirmLabel || t("Confirm"),
      theme: options.danger ? "danger" : "default",
      cancelBtn: t("Cancel"),
      placement: "center",
      width: "min(480px, calc(100vw - 32px))",
      dialogClassName: "app-confirm-dialog",
      closeOnEscKeydown: true,
      closeOnOverlayClick: false,
      onOpened: () => {
        document
          .querySelector<HTMLButtonElement>(
            ".app-confirm-dialog .t-dialog__footer button",
          )
          ?.focus();
      },
      onConfirm: () => finish(true),
      onClose: () => finish(false),
    });
    function finish(confirmed: boolean) {
      dialog.destroy();
      trigger?.focus();
      resolve(confirmed);
    }
  });
}
