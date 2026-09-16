package com.intersystems.kafka.connect.iris.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/**
 * This is the real-partition-support piece of the connector: proof that a
 * multi-table source distributes across tasks instead of running as one
 * unsplittable unit (the specific gap the community critique calls out in
 * IRIS's own built-in Kafka source adapters).
 */
class TaskPartitionerTest {

    @Test
    void fewerTablesThanTasksGivesOneTablePerTask() {
        List<List<String>> groups = TaskPartitioner.partition(List.of("A", "B"), 5);
        assertEquals(2, groups.size(), "should not create empty task groups just because tasks.max is higher");
        assertEquals(List.of(List.of("A"), List.of("B")), groups);
    }

    @Test
    void moreTablesThanTasksSpreadsRoundRobin() {
        List<List<String>> groups = TaskPartitioner.partition(List.of("A", "B", "C", "D", "E"), 2);
        assertEquals(2, groups.size());
        assertEquals(List.of("A", "C", "E"), groups.get(0));
        assertEquals(List.of("B", "D"), groups.get(1));
    }

    @Test
    void everyTableIsAssignedExactlyOnce() {
        List<String> tables = List.of("t1", "t2", "t3", "t4", "t5", "t6", "t7");
        List<List<String>> groups = TaskPartitioner.partition(tables, 3);

        List<String> flattened = groups.stream().flatMap(List::stream).collect(Collectors.toList());
        assertEquals(tables.size(), flattened.size());
        assertTrue(flattened.containsAll(tables) && tables.containsAll(flattened));
    }

    @Test
    void groupSizesDifferByAtMostOne() {
        List<String> tables = List.of("t1", "t2", "t3", "t4", "t5", "t6", "t7");
        List<List<String>> groups = TaskPartitioner.partition(tables, 3);

        int min = groups.stream().mapToInt(List::size).min().orElseThrow();
        int max = groups.stream().mapToInt(List::size).max().orElseThrow();
        assertTrue(max - min <= 1, "expected balanced groups, got sizes " + groups.stream().map(List::size).toList());
    }

    @Test
    void singleTaskGetsEveryTable() {
        List<String> tables = List.of("t1", "t2", "t3");
        List<List<String>> groups = TaskPartitioner.partition(tables, 1);
        assertEquals(1, groups.size());
        assertEquals(tables, groups.get(0));
    }

    @Test
    void rejectsEmptyTableList() {
        assertThrows(IllegalArgumentException.class, () -> TaskPartitioner.partition(List.of(), 3));
    }

    @Test
    void rejectsNonPositiveMaxTasks() {
        assertThrows(IllegalArgumentException.class, () -> TaskPartitioner.partition(List.of("A"), 0));
    }
}
