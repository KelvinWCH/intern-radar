import type { ResumeLink } from './models/resume-link.models';

export function resumeLink(original: string): ResumeLink {
  const text = original.trim();
  const fallback: ResumeLink = { label: original, url: null, original };
  if (!text || /[\s\\]/u.test(text) || text.startsWith('/')) {
    return fallback;
  }
  const destination = /^[a-z][a-z\d+.-]*:/iu.test(text) ? text : `https://${text}`;
  try {
    const parsed = new URL(destination);
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      !parsed.hostname.includes('.') ||
      parsed.username ||
      parsed.password
    ) {
      return fallback;
    }
    let label = original;
    if (['linkedin.com', 'www.linkedin.com'].includes(parsed.hostname)) {
      label = 'LinkedIn';
    } else if (['github.com', 'www.github.com'].includes(parsed.hostname)) {
      label = 'GitHub';
    }
    return { label, url: destination, original };
  } catch {
    return fallback;
  }
}

export function profileLink(url: string, label?: string | null): ResumeLink {
  const link = resumeLink(url);
  if (!link.url) {
    return link;
  }
  const parsed = new URL(link.url);
  return { ...link, label: label ?? parsed.hostname.replace(/^www\./u, '') + parsed.pathname };
}
