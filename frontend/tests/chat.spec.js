import { test, expect } from '@playwright/test';

const headers = {
  'access-control-allow-origin': 'http://127.0.0.1:5173',
  'access-control-allow-methods': 'POST, OPTIONS',
  'access-control-allow-headers': 'Content-Type',
};

async function mockChat(page, handler) {
  await page.route('http://127.0.0.1:8000/chat', async (route) => {
    if (route.request().method() === 'OPTIONS') {
      return route.fulfill({ status: 204, headers });
    }
    await handler(route);
  });
}

async function reply(route, body, status = 200) {
  await route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) });
}

async function send(page, message) {
  await page.getByRole('textbox', { name: 'Message PayHash' }).fill(message);
  await page.getByRole('button', { name: 'Send', exact: true }).click();
}

test('sends a message, shows loading, blocks duplicates, and sends completed memory', async ({ page }) => {
  const bodies = [];
  let releaseFirst;
  const waitForRelease = new Promise((resolve) => { releaseFirst = resolve; });
  await mockChat(page, async (route) => {
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 1) await waitForRelease;
    await reply(route, { reply: bodies.length === 1 ? 'TXN100235 is pending.' : 'Sara Khan received it.' });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await send(page, 'Check TXN100235');
  await expect(page.getByRole('status')).toHaveText('Thinking...');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'New chat' })).toBeDisabled();
  await expect(page.getByRole('textbox')).toBeDisabled();
  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0]).toEqual({ message: 'Check TXN100235', history: [] });
  releaseFirst();
  await expect(page.getByText('TXN100235 is pending.', { exact: true })).toBeVisible();
  await page.getByRole('textbox').fill('Who received it?');
  await page.getByRole('textbox').press('Enter');
  await expect(page.getByText('Sara Khan received it.', { exact: true })).toBeVisible();
  expect(bodies[1]).toEqual({ message: 'Who received it?', history: [{ question: 'Check TXN100235', answer: 'TXN100235 is pending.' }] });
  await expect(page.getByRole('textbox')).toHaveValue('');
  await expect(page.getByRole('textbox')).toBeFocused();
});

test('keeps exactly the latest ten successful exchanges, scrolls, and resets', async ({ page }) => {
  const bodies = [];
  await mockChat(page, async (route) => {
    bodies.push(route.request().postDataJSON());
    await reply(route, { reply: `Answer ${bodies.length}` });
  });
  await page.goto('/');
  for (let i = 1; i <= 12; i += 1) {
    await send(page, `Question ${i}`);
    await expect(page.getByText(`Answer ${i}`, { exact: true })).toBeVisible();
  }
  expect(bodies[11].history).toHaveLength(10);
  expect(bodies[11].history[0]).toEqual({ question: 'Question 2', answer: 'Answer 2' });
  await expect(page.getByText('Question 1', { exact: true })).toHaveCount(0);
  await expect(page.locator('.exchange')).toHaveCount(10);
  expect(await page.getByRole('log').evaluate((el) => el.scrollHeight - el.clientHeight - el.scrollTop)).toBeLessThan(3);
  await page.getByRole('button', { name: 'New chat' }).click();
  await expect(page.locator('.exchange')).toHaveCount(0);
  await send(page, 'Fresh start');
  await expect(page.getByText('Answer 13', { exact: true })).toBeVisible();
  expect(bodies[12].history).toEqual([]);
  await page.reload();
  await expect(page.locator('.exchange')).toHaveCount(0);
});

test('handles rate limits without saving errors or losing the draft', async ({ page }) => {
  const bodies = [];
  await mockChat(page, async (route) => {
    bodies.push(route.request().postDataJSON());
    if (bodies.length === 2) return reply(route, { detail: 'Please wait before trying again.' }, 429);
    await reply(route, { reply: 'Successful answer' });
  });
  await page.goto('/');
  await send(page, 'First question');
  await expect(page.getByText('Successful answer', { exact: true })).toBeVisible();
  await send(page, 'Failed question');
  await expect(page.getByRole('alert')).toContainText('Please wait');
  await expect(page.getByRole('textbox')).toHaveValue('Failed question');
  await expect(page.getByRole('textbox')).toBeEnabled();
  expect(bodies).toHaveLength(2);
  await send(page, 'Next question');
  await expect(page.locator('.exchange')).toHaveCount(2);
  expect(bodies[2].history).toEqual([{ question: 'First question', answer: 'Successful answer' }]);
});

test('shows network errors and rejects malformed success responses', async ({ page }) => {
  let count = 0;
  await mockChat(page, async (route) => {
    count += 1;
    if (count === 1) return route.abort('connectionrefused');
    if (count === 2) return reply(route, { reply: null });
    return reply(route, { detail: [{ msg: 'invalid input' }] }, 422);
  });
  await page.goto('/');
  await send(page, 'Hello');
  await expect(page.getByRole('alert')).toContainText('Could not reach support');
  await send(page, 'Hello');
  await expect(page.getByRole('alert')).toContainText('unexpected response');
  await send(page, 'Hello');
  await expect(page.getByRole('alert')).toContainText('could not be processed');
  await expect(page.locator('.exchange')).toHaveCount(0);
});

test('supports keyboard input, safe text rendering, and a narrow screen', async ({ page }) => {
  const scriptText = '<img src=x onerror=alert(1)>';
  await mockChat(page, (route) => reply(route, { reply: scriptText }));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('textbox').fill('   ');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await page.getByRole('textbox').fill('Line one');
  await page.getByRole('textbox').press('Shift+Enter');
  await page.getByRole('textbox').pressSequentially('Line two');
  await expect(page.getByRole('textbox')).toHaveValue('Line one\nLine two');
  await page.getByRole('textbox').press('Enter');
  await expect(page.getByText(scriptText, { exact: true })).toBeVisible();
  await expect(page.locator('.message-bubble img')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/mobile-chat.png', fullPage: true });
});

test('desktop layout renders without React errors and suggestions fill the draft', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Track a transaction' }).click();
  await expect(page.getByRole('textbox')).toHaveValue('What is the status of TXN100235?');
  await expect(page.locator('.exchange')).toHaveCount(0);
  await page.screenshot({ path: 'test-results/desktop-chat.png', fullPage: true });
  expect(errors).toEqual([]);
});
