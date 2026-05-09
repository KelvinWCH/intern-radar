import eslint from '@eslint/js';
import angular from 'angular-eslint';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', '.angular/**', 'coverage/**', 'node_modules/**'] },
  {
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: 'error' },
  },
  {
    files: ['src/**/*.ts'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      ...angular.configs.tsRecommended,
    ],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    processor: angular.processInlineTemplates,
    rules: {
      // types: no any, no unchecked casts, no surprises in conditions
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-type-assertion': 'error',
      '@typescript-eslint/consistent-type-assertions': [
        'error',
        { assertionStyle: 'as', objectLiteralTypeAssertions: 'never' },
      ],
      // nullable numbers and any are the ones that bite (0 and NaN are falsy)
      '@typescript-eslint/strict-boolean-expressions': [
        'error',
        { allowNullableBoolean: true, allowNullableString: true },
      ],
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/explicit-function-return-type': 'error',
      '@typescript-eslint/explicit-module-boundary-types': 'error',
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/prefer-readonly': 'error',
      '@typescript-eslint/ban-ts-comment': [
        'error',
        { 'ts-ignore': true, 'ts-nocheck': true, 'ts-expect-error': true, 'ts-check': false },
      ],
      // empty component classes are fine
      '@typescript-eslint/no-extraneous-class': ['error', { allowWithDecorator: true }],

      // readability
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-nested-ternary': 'error',
      'no-else-return': ['error', { allowElseIf: false }],
      // !!x stays allowed because typescript narrows on it and not on Boolean(x)
      'no-implicit-coercion': ['error', { boolean: false }],
      'no-param-reassign': 'error',
      'object-shorthand': 'error',
      'prefer-template': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
    },
  },
  {
    // fixture.nativeElement is typed any, and casting it is how angular tests read the dom
    files: ['src/**/*.spec.ts'],
    rules: { '@typescript-eslint/no-unsafe-type-assertion': 'off' },
  },
  {
    files: ['src/**/*.html'],
    extends: [...angular.configs.templateRecommended, ...angular.configs.templateAccessibility],
    rules: {
      '@angular-eslint/template/no-any': 'error',
      '@angular-eslint/template/prefer-control-flow': 'error',
      '@angular-eslint/template/prefer-self-closing-tags': 'error',
      '@angular-eslint/template/button-has-type': 'error',
    },
  },
  // last so it can switch off any rule that fights prettier
  {
    ...prettierRecommended,
    files: ['src/**/*.ts', 'src/**/*.html'],
  },
  {
    // prettier's config turns curly off, but braces on every if are safe with prettier
    files: ['src/**/*.ts'],
    rules: { curly: ['error', 'all'] },
  },
);
