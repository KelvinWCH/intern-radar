import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import type { Observable } from 'rxjs';
import { map, timeout } from 'rxjs';
import type { UserProfileState, UserProfile } from './models/user-profile.models';
import { parseUserProfileState } from './models/user-profile.models';
@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);
  get(): Observable<UserProfileState> {
    return this.http.get<unknown>('/api/profile').pipe(timeout(30000), map(parseUserProfileState));
  }
  save(profile: UserProfile, revision: number): Observable<UserProfileState> {
    return this.http
      .put<unknown>('/api/profile', { profile, revision })
      .pipe(timeout(30000), map(parseUserProfileState));
  }
}
