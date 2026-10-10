package com.geuttaeneolma.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Message;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private static final String HOME = "https://geuttaeneolma.com/";
    private static final String HOST = "geuttaeneolma.com";
    private WebView webView;
    private View errorView;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        FrameLayout root = new FrameLayout(this);
        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        errorView = makeErrorView();
        errorView.setVisibility(View.GONE);
        root.addView(errorView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return false;
                Uri uri = request.getUrl();
                if (isOurPage(uri)) return false;
                openExternal(uri);
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (isOurPage(Uri.parse(url)) && errorView.getTag() == null) {
                    errorView.setVisibility(View.GONE);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                if (request.isForMainFrame()) {
                    errorView.setTag("failed");
                    errorView.setVisibility(View.VISIBLE);
                }
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onCreateWindow(WebView view, boolean isDialog,
                                          boolean isUserGesture, Message resultMsg) {
                if (!isUserGesture) return false;
                // Affiliate links use target=_blank. Keep the ad's destination
                // outside our trusted site WebView, without a JavaScript bridge.
                WebView popup = new WebView(MainActivity.this);
                popup.setWebViewClient(new WebViewClient() {
                    private boolean opened = false;

                    private void navigate(Uri uri) {
                        if (opened || uri == null || "about".equals(uri.getScheme())) return;
                        opened = true;
                        openExternal(uri);
                        popup.post(popup::destroy);
                    }

                    @Override
                    public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                        navigate(request.getUrl());
                        return true;
                    }

                    @Override
                    public void onPageStarted(WebView v, String url, android.graphics.Bitmap favicon) {
                        navigate(Uri.parse(url));
                    }
                });
                ((WebView.WebViewTransport) resultMsg.obj).setWebView(popup);
                resultMsg.sendToTarget();
                return true;
            }
        });

        loadPage(startUrl(getIntent()));
    }

    private boolean isOurPage(Uri uri) {
        return uri != null && "https".equalsIgnoreCase(uri.getScheme())
                && HOST.equalsIgnoreCase(uri.getHost());
    }

    private String startUrl(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        return isOurPage(data) ? data.toString() : HOME;
    }

    private void loadPage(String url) {
        errorView.setTag(null);
        errorView.setVisibility(View.GONE);
        webView.loadUrl(url);
    }

    private void openExternal(Uri uri) {
        if (uri == null || !("https".equalsIgnoreCase(uri.getScheme())
                || "http".equalsIgnoreCase(uri.getScheme()))) return;
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri)
                    .addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "링크를 열 브라우저가 없습니다.", Toast.LENGTH_SHORT).show();
        }
    }

    private View makeErrorView() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setPadding(32, 32, 32, 32);
        box.setBackgroundColor(Color.rgb(251, 252, 253));

        TextView message = new TextView(this);
        message.setText("사이트에 연결할 수 없습니다.\n인터넷 연결을 확인하고 다시 시도해 주세요.");
        message.setTextColor(Color.rgb(20, 32, 43));
        message.setTextSize(17);
        message.setGravity(Gravity.CENTER);
        box.addView(message);

        Button retry = new Button(this);
        retry.setText("다시 시도");
        retry.setOnClickListener(v -> loadPage(webView.getUrl() == null ? HOME : webView.getUrl()));
        box.addView(retry);
        return box;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadPage(startUrl(intent));
    }

    @Override
    public void onBackPressed() {
        if (errorView.getVisibility() == View.VISIBLE) {
            errorView.setVisibility(View.GONE);
            return;
        }
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            ((ViewGroup) webView.getParent()).removeView(webView);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
