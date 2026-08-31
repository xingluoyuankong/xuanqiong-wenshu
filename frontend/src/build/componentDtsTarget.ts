/**
 * Keep declaration generation out of production builds.
 *
 * `unplugin-vue-components` rewrites the declaration file while Vite is
 * building. On Windows that write can race another process inspecting the
 * checked-in declaration file, making an otherwise valid production build
 * fail with an `UNKNOWN` file-open error. The declarations are generated in
 * development and checked in; production builds only consume the snapshot.
 */
export function componentDtsTarget(command: 'serve' | 'build'): string | false {
  return command === 'serve' ? 'src/components.d.ts' : false
}
