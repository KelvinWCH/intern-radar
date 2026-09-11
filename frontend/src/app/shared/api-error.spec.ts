import { HttpErrorResponse } from '@angular/common/http';
import { apiError } from './api-error';

describe('apiError', (): void => {
  it('reports field errors', (): void => {
    const error = new HttpErrorResponse({
      status: 422,
      error: {
        detail: [
          {
            loc: ['body', 'cleaned_description'],
            msg: 'String should have at most 20000 characters',
            input: 'private source text',
          },
          { loc: ['body', 'research_ai_options', 'model'], msg: 'Field required' },
        ],
      },
    });
    expect(apiError(error, 'Failed')).toBe(
      'Cleaned description: String should have at most 20000 characters; Research ai options > Model: Field required',
    );
    expect(apiError(error, 'Failed')).not.toContain('private source text');
  });

  it('detects a restarting backend', (): void => {
    expect(apiError(new HttpErrorResponse({ status: 503 }), 'Could not save. Edits kept.')).toBe(
      'Could not save. Edits kept. The backend is unavailable or restarting (HTTP 503); try again shortly.',
    );
    expect(
      apiError(
        new HttpErrorResponse({ status: 503, error: { detail: 'PDF compiler is unavailable.' } }),
        'Failed',
      ),
    ).toBe('PDF compiler is unavailable.');
    expect(apiError(new HttpErrorResponse({ status: 500 }), 'Failed')).toBe('Failed');
  });
});
