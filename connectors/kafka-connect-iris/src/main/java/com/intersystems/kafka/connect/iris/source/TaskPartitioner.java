package com.intersystems.kafka.connect.iris.source;

import java.util.ArrayList;
import java.util.List;

/**
 * Splits a list of tables into up to {@code maxTasks} roughly-even groups.
 *
 * <p>This is the direct answer to the "no real partition support" half of
 * the community critique this connector exists to address: IRIS's built-in
 * Kafka source adapters run a whole configuration as one unit, so a
 * multi-table source never parallelizes past a single task. Here, each
 * table is an independent, independently-offset unit of work, and this
 * class is what {@link IrisSourceConnector#taskConfigs} uses to spread
 * them across tasks.
 *
 * <p>Extracted as its own class (rather than inlined in the connector) so
 * the distribution logic can be unit-tested directly without touching the
 * Connect framework's {@code Connector} lifecycle at all.
 */
public final class TaskPartitioner {

    private TaskPartitioner() {
    }

    /**
     * @param tables   tables to distribute; must not be empty
     * @param maxTasks the {@code tasks.max} value; must be at least 1
     * @return a list of 1..min(maxTasks, tables.size()) groups, each a
     *     non-empty subset of {@code tables}, with sizes differing by at
     *     most 1 and original relative ordering preserved within a group
     */
    public static List<List<String>> partition(List<String> tables, int maxTasks) {
        if (tables == null || tables.isEmpty()) {
            throw new IllegalArgumentException("tables must not be empty");
        }
        if (maxTasks < 1) {
            throw new IllegalArgumentException("maxTasks must be at least 1");
        }

        int numGroups = Math.min(maxTasks, tables.size());
        List<List<String>> groups = new ArrayList<>(numGroups);
        for (int i = 0; i < numGroups; i++) {
            groups.add(new ArrayList<>());
        }

        // Round-robin rather than contiguous slicing: with tables ordered
        // e.g. by expected write volume, contiguous slicing could load one
        // task with every hot table. Round-robin spreads that risk out
        // without needing any knowledge of per-table load.
        for (int i = 0; i < tables.size(); i++) {
            groups.get(i % numGroups).add(tables.get(i));
        }
        return groups;
    }
}
