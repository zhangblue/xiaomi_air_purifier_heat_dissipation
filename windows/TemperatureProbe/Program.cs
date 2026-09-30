using System.Text.Json;
using LibreHardwareMonitor.Hardware;

namespace TemperatureProbe;

public sealed class UpdateVisitor : IVisitor
{
    public void VisitComputer(IComputer computer) => computer.Traverse(this);

    public void VisitHardware(IHardware hardware)
    {
        hardware.Update();
        foreach (IHardware child in hardware.SubHardware)
            child.Accept(this);
    }

    public void VisitSensor(ISensor sensor) { }
    public void VisitParameter(IParameter parameter) { }
}

public sealed record SensorReading(string Name, float? Value);

public static class SensorSelector
{
    public static float SelectCpuTemperature(IEnumerable<SensorReading> readings)
    {
        SensorReading[] valid = readings
            .Where(reading => reading.Value is float value &&
                              float.IsFinite(value) && value >= 0 && value <= 125)
            .ToArray();

        SensorReading? package = valid.FirstOrDefault(reading =>
            string.Equals(reading.Name, "CPU Package", StringComparison.OrdinalIgnoreCase));
        if (package is not null)
            return package.Value!.Value;

        float[] cores = valid
            .Where(reading => reading.Name.StartsWith("CPU Core", StringComparison.OrdinalIgnoreCase))
            .Select(reading => reading.Value!.Value)
            .ToArray();
        if (cores.Length == 0)
            throw new InvalidOperationException("No valid CPU temperature sensor was found");

        return (float)cores.Average(value => (double)value);
    }
}

public static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] != "--json")
        {
            Console.Error.WriteLine("Usage: TemperatureProbe --json");
            return 2;
        }

        try
        {
            Computer computer = new() { IsCpuEnabled = true };
            try
            {
                computer.Open();
                computer.Accept(new UpdateVisitor());
                SensorReading[] readings = computer.Hardware
                    .Where(hardware => hardware.HardwareType == HardwareType.Cpu)
                    .SelectMany(CpuTemperatureReadings)
                    .ToArray();
                float temperature = SensorSelector.SelectCpuTemperature(readings);
                Console.WriteLine(JsonSerializer.Serialize(new { temperature_c = temperature }));
                return 0;
            }
            finally
            {
                computer.Close();
            }
        }
        catch (Exception)
        {
            Console.Error.WriteLine("CPU temperature could not be read");
            return 1;
        }
    }

    private static IEnumerable<SensorReading> CpuTemperatureReadings(IHardware hardware)
    {
        foreach (ISensor sensor in hardware.Sensors)
        {
            if (sensor.SensorType == SensorType.Temperature)
                yield return new SensorReading(sensor.Name, sensor.Value);
        }

        foreach (IHardware child in hardware.SubHardware)
        {
            foreach (SensorReading reading in CpuTemperatureReadings(child))
                yield return reading;
        }
    }
}
