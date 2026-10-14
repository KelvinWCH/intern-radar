import { Component, input } from '@angular/core';
import type { CoverLetter } from '../models/document.models';
@Component({
  selector: 'app-cover-letter-preview',
  template: `<article>
    <header>
      <h3>{{ letter().name }}</h3>
      <p>
        @if (letter().email; as email) {
          <a [href]="'mailto:' + email">{{ email }}</a>
        }
        @if (letter().phone; as phone) {
          <span> | </span><a [href]="phoneUrl(phone)">{{ phone }}</a>
        }
        {{ letter().email && letter().location ? ' | ' : '' }}{{ letter().location }}
      </p>
    </header>
    <p>
      <strong>{{ letter().company }}</strong
      ><br />Re: {{ letter().job_title }}
    </p>
    <p>{{ letter().greeting }}</p>
    @for (paragraph of letter().paragraphs; track $index) {
      <p>{{ paragraph }}</p>
    }
    <hr />
    <p>{{ letter().closing }}<br /><br />{{ letter().name }}</p>
  </article>`,
  styles: `
    article {
      background: white;
      padding: 36px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-family: Georgia, serif;
      color: #282025;
      font-size: 14px;
      line-height: 1.8;
      overflow-wrap: anywhere;
    }
    hr {
      border: 0;
      border-top: 1px solid var(--line);
      margin: 24px 0;
    }
    header {
      text-align: center;
      border-bottom: 1px solid var(--line);
      margin-bottom: 28px;
    }
    header h3 {
      font-size: 25px;
      margin: 0;
    }
    header p {
      font-size: 12px;
    }
    @media (max-width: 500px) {
      article {
        padding: 22px;
      }
    }
  `,
})
export class CoverLetterPreview {
  protected phoneUrl(phone: string): string {
    return `tel:${phone.replace(/[^+0-9]/g, '')}`;
  }
  readonly letter = input.required<CoverLetter>();
}
