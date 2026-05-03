/**rewriteStream
 * Reads from a source ReadableStream and returns a new ReadableStream where the processor transforms source data and pushes new values to the new stream; if no value is returned, nothing is pushed
 * @param stream
 * @param processor
 */
export const rewriteStream = (stream: ReadableStream, processor: (data: any, controller: ReadableStreamController<any>) => Promise<any>): ReadableStream => {
  const reader = stream.getReader()

  return new ReadableStream({
    async start(controller) {
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) {
            controller.close()
            break
          }

          const processed = await processor(value, controller)
          if (processed !== undefined) {
            controller.enqueue(processed)
          }
        }
      } catch (error) {
        controller.error(error)
      } finally {
        reader.releaseLock()
      }
    }
  })
}
