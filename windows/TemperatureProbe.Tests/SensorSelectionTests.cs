using TemperatureProbe;
using Xunit;

namespace TemperatureProbe.Tests;

public class SensorSelectionTests
{
    [Fact]
    public void PackageTemperatureTakesPriorityOverCoreReadings()
    {
        SensorReading[] readings =
        [
            new("CPU Core #1", 60),
            new("CPU Package", 72),
            new("CPU Core #2", 64),
        ];

        Assert.Equal(72f, SensorSelector.SelectCpuTemperature(readings));
    }

    [Fact]
    public void UsesAverageCoreTemperatureWhenPackageUnavailable()
    {
        SensorReading[] readings =
        [
            new("CPU Core #1", 60),
            new("CPU Core #2", 64),
            new("CPU Package", null),
        ];

        Assert.Equal(62f, SensorSelector.SelectCpuTemperature(readings));
    }

    [Fact]
    public void ExcludesInvalidValuesFromSelection()
    {
        SensorReading[] readings =
        [
            new("CPU Package", float.NaN),
            new("CPU Core #1", -2),
            new("CPU Core #2", 126),
            new("CPU Core #3", 66),
            new("Motherboard", 75),
        ];

        Assert.Equal(66f, SensorSelector.SelectCpuTemperature(readings));
    }

    [Fact]
    public void ThrowsWhenNoUsableCpuTemperatureExists()
    {
        Assert.Throws<InvalidOperationException>(() =>
            SensorSelector.SelectCpuTemperature(
            [new SensorReading("Motherboard", 55), new SensorReading("CPU Package", float.PositiveInfinity)]));
    }
}
