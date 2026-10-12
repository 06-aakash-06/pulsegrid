import { feedbackMessage } from "./api";
import type { AdmissionFeedbackProps } from "./contracts";

export function AdmissionFeedback({
  error,
  onRetry,
  retryLabel = "Try again",
  operationLabel,
}: AdmissionFeedbackProps) {
  return (
    <div className="phase4-feedback" role="status" aria-live="polite">
      <p>{feedbackMessage(error, operationLabel)}</p>
      {onRetry && (
        <button className="button button--secondary button--small" type="button" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}
