import { constants } from 'node:fs';
import { access, stat } from 'node:fs/promises';
import { isAbsolute } from 'node:path';

function failure(name, message, cause) {
  const error = new Error(message, { cause });
  error.name = name;
  return error;
}

/** A fresh Chrome process; package resolution remains the caller's explicit playwright-core import. */
export async function launchChrome(chromium, options = {}, environment = process.env) {
  const executablePath = environment.DODREAM_CHROME_EXECUTABLE;
  if (executablePath !== undefined) {
    try {
      if (!isAbsolute(executablePath) || !(await stat(executablePath)).isFile()) throw new Error('Not an executable file');
      await access(executablePath, constants.X_OK);
    } catch (cause) {
      throw failure('ChromeExecutableConfigurationError',
        'DODREAM_CHROME_EXECUTABLE must name an existing executable file by absolute path; no fallback was attempted.', cause);
    }
  }
  const launchOptions = { ...options };
  delete launchOptions.channel;
  delete launchOptions.executablePath;
  Object.assign(launchOptions, executablePath === undefined ? { channel: 'chrome' } : { executablePath });
  try {
    return await chromium.launch(launchOptions);
  } catch (cause) {
    const unavailable = /distribution ['"]chrome['"] is not found|executable doesn['’]t exist|ENOENT/i.test(cause.message ?? '');
    throw failure(unavailable ? 'ChromeUnavailableError' : 'ChromeLaunchError',
      'Chrome could not start. Use an installed Chrome channel or set DODREAM_CHROME_EXECUTABLE to an executable Chrome file. No browser was downloaded or alternative attempted.', cause);
  }
}
