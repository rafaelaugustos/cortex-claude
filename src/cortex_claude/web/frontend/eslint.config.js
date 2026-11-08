import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import vue from 'eslint-plugin-vue'
export default tseslint.config(
 { ignores: ['dist', 'node_modules', 'playwright-report', 'test-results'] },
 js.configs.recommended,
 ...tseslint.configs.recommended,
 ...vue.configs['flat/essential'],
 { files: ['**/*.ts', '**/*.vue'], languageOptions: { globals: { ...globals.browser, ...globals.node }, parserOptions: { parser: tseslint.parser } }, rules: { '@typescript-eslint/no-explicit-any': 'off' } },
 { files: ['**/*.js'], languageOptions: { globals: globals.node } },
)
