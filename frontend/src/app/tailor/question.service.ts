import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { map } from 'rxjs';
import type { QuestionAnswer, QuestionRequest } from './models/question.models';
import { parseQuestionAnswer } from './models/question.models';
import { AiDefaults } from '../settings/ai-defaults';

@Injectable({ providedIn: 'root' })
export class QuestionService {
  private readonly http = inject(HttpClient);
  private readonly preferences = inject(AiDefaults);

  answer(request: QuestionRequest): Observable<QuestionAnswer> {
    return this.http
      .post<unknown>('/api/resumes/questions/answer', {
        ...request,
        ai_options: this.preferences.resolve('answer', request.ai_options),
      })
      .pipe(
        map((value): QuestionAnswer => {
          const answer = parseQuestionAnswer(value);
          if (answer.question !== request.question || answer.word_count > request.max_words) {
            throw new Error('The answer does not match the requested question or word limit.');
          }
          return answer;
        }),
      );
  }
}
