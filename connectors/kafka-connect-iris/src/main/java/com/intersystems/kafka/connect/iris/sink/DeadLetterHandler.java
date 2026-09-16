package com.intersystems.kafka.connect.iris.sink;

import org.apache.kafka.connect.sink.ErrantRecordReporter;
import org.apache.kafka.connect.sink.SinkRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The dead-letter path for records {@link IrisSinkTask} could not write.
 *
 * <p>This deliberately does not implement its own Kafka producer to send
 * failed records to a DLQ topic. Kafka Connect has had a framework-level
 * dead-letter-queue mechanism since KIP-610 (Connect 2.6):
 * {@code SinkTaskContext.errantRecordReporter()}, wired up by the worker
 * from the connector's {@code errors.tolerance} / {@code errors.deadletterqueue.*}
 * configs. Reimplementing that here would duplicate the framework's own
 * producer, its own configs, and its own delivery guarantees, and would
 * very likely get at least one of those subtly wrong. Using the framework
 * hook is both less code and more correct.
 *
 * <p>The fallback when no reporter is configured (older Connect runtime,
 * or the worker/connector simply didn't turn DLQ routing on) is a clearly
 * visible ERROR log per record -- not a silent drop, and not a task
 * failure, since failing the whole task on one bad record is exactly the
 * behavior a dead-letter path exists to avoid.
 */
public class DeadLetterHandler {

    private static final Logger log = LoggerFactory.getLogger(DeadLetterHandler.class);

    private final ErrantRecordReporter reporter;

    public DeadLetterHandler(ErrantRecordReporter reporter) {
        this.reporter = reporter;
    }

    public void deadLetter(SinkRecord record, Throwable cause) {
        if (reporter != null) {
            reporter.report(record, cause);
            log.warn("Routed record (topic={}, partition={}, offset={}) to the dead-letter queue: {}",
                    record.topic(), record.kafkaPartition(), record.kafkaOffset(), cause.getMessage());
        } else {
            log.error("No ErrantRecordReporter configured (errors.tolerance/errors.deadletterqueue.topic.name "
                    + "not set on this connector) -- DROPPING record (topic={}, partition={}, offset={}) "
                    + "that failed to write: {}",
                    record.topic(), record.kafkaPartition(), record.kafkaOffset(), cause.getMessage(), cause);
        }
    }
}
