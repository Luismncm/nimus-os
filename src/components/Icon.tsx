/**
 * The one close/dismiss icon of the app. It draws in currentColor, so each button colors it by state,
 * and it is drawn centered in its own box (a text "×" sits off-center depending on the font).
 */
export function CloseIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}
