import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
import { htmlText, htmlLines } from '../src/utils/htmlText.ts';

// Exercise the templates used by the actual editor/modals, not a copied template.
function renderTemplate(file: string, marker: string, values: Record<string, unknown>) {
  const path = new URL(`../src/pages/${file}.tsx`, import.meta.url);
  const source = fs.readFileSync(path, 'utf8');
  const tree = ts.createSourceFile(path.pathname, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let template: ts.TemplateExpression | undefined;
  function visit(node: ts.Node) {
    if (ts.isTemplateExpression(node) && node.getText(tree).includes(marker) && !template) template = node;
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(template, marker);
  const compiled = ts.transpileModule(`const render = () => ${template!.getText(tree)};`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return Function(...Object.keys(values), 'htmlText', 'htmlLines', `${compiled}; return render();`)(
    ...Object.values(values), htmlText, htmlLines) as string;
}

const attack = '\"><img src=x onerror=alert(1)><script>alert(2)</script>&';
const safe = '&quot;&gt;&lt;img src=x onerror=alert(1)&gt;&lt;script&gt;alert(2)&lt;/script&gt;&amp;';
test('plain text and attributes preserve characters without creating HTML', () => {
  assert.equal(htmlText(attack), safe);
  assert.equal(htmlLines('<em>text</em>\nnext'), '&lt;em&gt;text&lt;/em&gt;<br/>next');
});
test('chapter merge modal escapes title in text and quoted input value', () => {
  const html = renderTemplate('AdvancedEditor', 'id="mergedTitle"', { selected: [{ title: attack }], mergedTitle: attack });
  assert.ok(html.includes(`value="${safe}"`));
  assert.ok(html.includes(`• ${safe}`));
  assert.equal(html.includes('<img'), false);
});
test('generated quiz text cannot become editor markup', () => {
  const html = renderTemplate('AdvancedEditor', '${htmlText(q.title)}', {
    q: { title: attack, content: attack, correct_answer: attack, chapter_reference: attack }, typeLabel: attack,
  });
  assert.equal(html.includes('<script'), false);
  assert.equal(html.includes('<img'), false);
  assert.ok(html.includes(safe));
});
test('share modal treats persisted names and material title as text', () => {
  const html = renderTemplate('ClassroomList', '공유한 학생', { material: { title: attack }, classroomNames: attack, names: [attack] });
  assert.equal(html.includes('<img'), false);
  assert.equal(html.split(safe).length - 1, 3);
});
test('teacher pages do not log payloads or raw exception objects', () => {
  const directory = new URL('../src/pages/', import.meta.url);
  for (const name of fs.readdirSync(directory).filter(name => name.endsWith('.tsx'))) {
    const source = fs.readFileSync(new URL(name, directory), 'utf8');
    const tree = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(node: ts.Node) {
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) && node.expression.expression.getText(tree) === 'console') {
        assert.notEqual(node.expression.name.text, 'log', name);
        assert.equal(node.arguments.length, 1, name);
        assert.ok(ts.isStringLiteral(node.arguments[0]), name);
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
  }
  const sharing = fs.readFileSync(new URL('../src/component/MaterialSendModal2step.tsx', import.meta.url), 'utf8');
  assert.equal(/console\.(log|warn|error)\(/.test(sharing), false);
});
test('dynamic toast titles use SweetAlert text rendering and filenames are not HTML encoded', () => {
  for (const name of ['Join', 'ClassroomList']) {
    const source = fs.readFileSync(new URL(`../src/pages/${name}.tsx`, import.meta.url), 'utf8');
    const tree = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(node: ts.Node) {
      if (ts.isCallExpression(node) && node.expression.getText(tree) === 'Swal.fire') {
        const options = node.arguments[0];
        if (options && ts.isObjectLiteralExpression(options)) {
          for (const field of options.properties) {
            if (ts.isPropertyAssignment(field) && field.name.getText(tree) === 'title') {
              assert.ok(ts.isStringLiteral(field.initializer), `${name}: dynamic title must use titleText`);
            }
          }
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
  }
  const source = fs.readFileSync(new URL('../src/pages/ClassroomList.tsx', import.meta.url), 'utf8');
  assert.ok(source.includes('a.download = `${material.title}.docx`'));
});
