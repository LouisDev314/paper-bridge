import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      eqeqeq: ['error', 'always'],
      'no-duplicate-imports': ['error', { includeExports: true }],

      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
          ignoreRestSiblings: true,
        },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',

      'no-unused-expressions': 'off',
      complexity: ['warn', 20],

      indent: 'off',
      quotes: 'off',
      'no-multi-spaces': 'off',
      'linebreak-style': 'off',
      'object-curly-spacing': 'off',
      'eol-last': 'off',
      'comma-dangle': 'off',
      'nonblock-statement-body-position': 'off',
    },
  },
  globalIgnores([
    '.next/**',
    'out/**',
    'build/**',
    'next-env.d.ts',
    'components/ui/**',
  ]),
]);

export default eslintConfig;
