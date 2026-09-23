import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { DownloadConfirmationDetails } from '@/lib/hooks/engineCapabilityRules';

function formatDownloadSize(sizeMb: number): string {
  return sizeMb >= 1024 ? `${(sizeMb / 1024).toFixed(1)} GB` : `${Math.round(sizeMb)} MB`;
}

interface DownloadConfirmDialogProps {
  details: DownloadConfirmationDetails | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Asks before starting a model download for engines whose capability sets
 * `requires_download_confirmation` (FR-018, C1Q7), showing the declared download size and
 * any capability warning, such as too little memory (C1Q4), without blocking the download.
 */
export function DownloadConfirmDialog({
  details,
  onConfirm,
  onCancel,
}: DownloadConfirmDialogProps) {
  // Every way of closing (Download, Cancel, Escape, overlay) goes through onOpenChange once;
  // the ref records whether that close was the Download button.
  const confirmedRef = useRef(false);
  const { t } = useTranslation();
  const licenseKey =
    details?.commercialUse === true
      ? 'downloadConfirm.licenseCommercial'
      : details?.commercialUse === false
        ? 'downloadConfirm.licenseNoncommercial'
        : 'downloadConfirm.license';
  return (
    <AlertDialog
      open={!!details}
      onOpenChange={(open) => {
        if (open) return;
        const confirmed = confirmedRef.current;
        confirmedRef.current = false;
        if (confirmed) onConfirm();
        else onCancel();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t('downloadConfirm.title', { name: details?.displayName ?? '' })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {details
              ? t('downloadConfirm.size', { size: formatDownloadSize(details.sizeMb) })
              : null}
            {details?.licenseId ? ` ${t(licenseKey, { license: details.licenseId })}` : null}
          </AlertDialogDescription>
          {/* C1Q4: advisory only; Download stays enabled. */}
          {details?.warning ? (
            <p className="text-sm text-amber-600 dark:text-amber-400">{details.warning}</p>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => {
              confirmedRef.current = true;
            }}
          >
            {t('downloadConfirm.download')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
