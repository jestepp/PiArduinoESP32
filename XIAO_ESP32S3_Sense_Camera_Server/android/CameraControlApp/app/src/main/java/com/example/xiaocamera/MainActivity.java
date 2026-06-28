package com.example.xiaocamera;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final UUID SERVICE_UUID = UUID.fromString("b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201");
    private static final UUID CONFIG_UUID = UUID.fromString("b2b7f441-1c2a-45a8-a7c7-8fd6f7d90201");
    private TextView status;
    private EditText url;
    private EditText ssid;
    private EditText pass;
    private WebView webView;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic config;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestNeededPermissions();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(18, 18, 18, 18);
        root.setGravity(Gravity.CENTER_HORIZONTAL);

        status = new TextView(this);
        status.setText("Open the camera AP, then load http://169.254.4.1 or scan BLE.");
        root.addView(status);

        url = new EditText(this);
        url.setSingleLine(true);
        url.setText("http://169.254.4.1");
        root.addView(url);

        Button load = new Button(this);
        load.setText("Load Camera UI");
        load.setOnClickListener(v -> webView.loadUrl(url.getText().toString()));
        root.addView(load);

        ssid = new EditText(this);
        ssid.setHint("Router SSID");
        ssid.setSingleLine(true);
        root.addView(ssid);

        pass = new EditText(this);
        pass.setHint("Router password");
        pass.setSingleLine(true);
        root.addView(pass);

        Button scan = new Button(this);
        scan.setText("Scan BLE");
        scan.setOnClickListener(v -> startBleScan());
        root.addView(scan);

        Button send = new Button(this);
        send.setText("Send Wi-Fi Over BLE");
        send.setOnClickListener(v -> sendWifiConfig());
        root.addView(send);

        webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        root.addView(webView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        setContentView(root);
    }

    private void requestNeededPermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            requestPermissions(new String[]{
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT
            }, 10);
        } else {
            requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, 10);
        }
    }

    @SuppressLint("MissingPermission")
    private void startBleScan() {
        BluetoothManager manager = getSystemService(BluetoothManager.class);
        BluetoothAdapter adapter = manager.getAdapter();
        BluetoothLeScanner scanner = adapter.getBluetoothLeScanner();
        status.setText("Scanning for XIAO-S3-Camera...");
        scanner.startScan(new ScanCallback() {
            @Override
            public void onScanResult(int callbackType, ScanResult result) {
                BluetoothDevice device = result.getDevice();
                String name = device.getName();
                if ("XIAO-S3-Camera".equals(name)) {
                    scanner.stopScan(this);
                    status.setText("Connecting to " + name);
                    gatt = device.connectGatt(MainActivity.this, false, gattCallback);
                }
            }
        });
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int statusCode, int newState) {
            runOnUiThread(() -> status.setText("BLE connected; discovering services"));
            gatt.discoverServices();
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int statusCode) {
            BluetoothGattService service = gatt.getService(SERVICE_UUID);
            if (service != null) {
                config = service.getCharacteristic(CONFIG_UUID);
            }
            runOnUiThread(() -> status.setText(config == null ? "Config characteristic not found" : "BLE ready"));
        }
    };

    @SuppressLint("MissingPermission")
    private void sendWifiConfig() {
        if (gatt == null || config == null) {
            status.setText("Scan BLE first.");
            return;
        }
        writeLine("ssid=" + ssid.getText());
        writeLine("pass=" + pass.getText());
        writeLine("reboot=1");
        status.setText("Wi-Fi sent. Reconnect to LAN after reboot.");
    }

    @SuppressLint("MissingPermission")
    private void writeLine(String line) {
        config.setValue(line.getBytes(StandardCharsets.UTF_8));
        gatt.writeCharacteristic(config);
        try {
            Thread.sleep(250);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}
