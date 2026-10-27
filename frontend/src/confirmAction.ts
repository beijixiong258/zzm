import { DialogPlugin } from "tdesign-vue-next";
import { t } from "./i18n";

export function confirmAction(message: string): Promise<boolean> {
  const trigger = document.activeElement as HTMLElement | null;
  return new Promise((resolve) => {
    const dialog = DialogPlugin.confirm({
      header: t("Confirm"),
      body: message,
      confirmBtn: t("Confirm"),
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
