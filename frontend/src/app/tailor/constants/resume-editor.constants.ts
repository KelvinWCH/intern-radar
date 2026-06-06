export const previewDelayMs = 1200;

export const resumeLockedReasons: Readonly<Record<string, string>> = {
  running: 'Tailoring is still running. You can edit the resume once it finishes.',
  awaiting_review:
    'This attempt is waiting for your review. Resolve it on the documents page, then edit the resume.',
};
