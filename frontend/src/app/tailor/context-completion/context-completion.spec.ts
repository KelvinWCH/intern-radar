import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { ContextCompletion } from './context-completion';

describe('Context sentence completion', (): void => {
  let fixture: ComponentFixture<ContextCompletion>;
  let target: HTMLTextAreaElement;
  let http: HttpTestingController;

  function type(value: string): void {
    target.value = value;
    target.setSelectionRange(value.length, value.length);
    target.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }

  function key(value: string, shiftKey = false): KeyboardEvent {
    const event = new KeyboardEvent('keydown', {
      key: value,
      shiftKey,
      bubbles: true,
      cancelable: true,
    });
    target.dispatchEvent(event);
    return event;
  }

  function suggest(continuation = ' use Python.'): void {
    vi.advanceTimersByTime(901);
    http
      .expectOne('/api/resumes/questions/complete')
      .flush({ continuation, model: 'chosen-model' });
    fixture.detectChanges();
  }

  beforeEach(async (): Promise<void> => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(ContextCompletion);
    target = document.createElement('textarea');
    target.id = 'context';
    target.maxLength = 2000;
    document.body.append(target);
    fixture.componentRef.setInput('textarea', target);
    fixture.componentRef.setInput('context', {
      purpose: 'context',
      question: 'What skills?',
      ai_options: { model: 'chosen-model' },
    });
    http = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    vi.useFakeTimers();
  });

  afterEach((): void => {
    fixture.destroy();
    target.remove();
    http.verify();
    vi.useRealTimers();
    localStorage.removeItem('intern-radar.ai-defaults.v1');
  });

  it('suggests and accepts with tab', (): void => {
    target.focus();
    type('I');
    vi.advanceTimersByTime(500);
    type('I can');
    vi.advanceTimersByTime(500);
    http.expectNone('/api/resumes/questions/complete');
    vi.advanceTimersByTime(401);
    const request = http.expectOne('/api/resumes/questions/complete');
    expect(request.request.body).toEqual({
      text: 'I can',
      purpose: 'context',
      question: 'What skills?',
      ai_options: { model: 'chosen-model' },
    });
    request.flush({ continuation: ' use Python.', model: 'chosen-model' });
    fixture.detectChanges();
    expect(target.value).toBe('I can');
    const input = vi.fn();
    target.addEventListener('input', input);
    expect(key('Tab').defaultPrevented).toBe(true);
    expect(target.value).toBe('I can use Python.');
    expect(target.selectionStart).toBe(target.value.length);
    expect(input).toHaveBeenCalledOnce();
    expect(key('Tab').defaultPrevented).toBe(false);
    vi.advanceTimersByTime(1200);
    http.expectNone('/api/resumes/questions/complete');
  });

  it('drops stale suggestions', (): void => {
    target.focus();
    type('I');
    vi.advanceTimersByTime(901);
    const stale = http.expectOne('/api/resumes/questions/complete');
    type('I can');
    expect(stale.cancelled).toBe(true);
    suggest();
    target.setSelectionRange(0, 0);
    document.dispatchEvent(new Event('selectionchange'));
    expect(key('Tab').defaultPrevented).toBe(false);
    type('I could');
    suggest();
    target.blur();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.suggestion-text')).toBeNull();
  });
});
