import { useRef } from 'react';
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
 * `requires_download_confirmation` (FR-018, C1Q7), showing the declared download size.
 */
export function DownloadConfirmDialog({
  details,
  onConfirm,
  onCancel,
}: DownloadConfirmDialogProps) {
  // Every way of closing (Download, Cancel, Escape, overlay) goes through onOpenChange once;
  // the ref records whether that close was the Download button.
  const confirmedRef = useRef(false);
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
          <AlertDialogTitle>Download {details?.displayName}?</AlertDialogTitle>
          <AlertDialogDescription>
            {details
              ? `This downloads about ${formatDownloadSize(details.sizeMb)} before it can be used.`
              : null}
            {details?.licenseId
              ? ` Licence: ${details.licenseId}${
                  details.commercialUse === true
                    ? ', commercial use allowed.'
                    : details.commercialUse === false
                      ? ', noncommercial use only.'
                      : '.'
                }`
              : null}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => {
              confirmedRef.current = true;
            }}
          >
            Download
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
