# Sentinel Hub API Key Setup Guide

This guide provides step-by-step instructions for obtaining a Sentinel Hub API key to enable live Sentinel-2 satellite data in JalDrishti.

## What is Sentinel Hub?

Sentinel Hub is a cloud-based platform that provides access to satellite imagery from Copernicus (Sentinel-1, Sentinel-2, Sentinel-3, Sentinel-5P) and other satellite missions. It offers:

- **Processing API**: Process satellite data on-the-fly with custom evalscripts
- **Catalog API**: Search and discover available satellite imagery
- **Batch Processing**: Process large areas and time ranges
- **Web Services**: OGC WMS/WMTS services for integration

## Step-by-Step API Key Acquisition

### Step 1: Create a Sentinel Hub Account

1. Visit https://www.sentinel-hub.com/
2. Click **"Sign up"** or **"Get started"**
3. Choose your account type:
   - **Free Trial**: 30-day trial with 30,000 processing units (PU)
   - **Paid Plans**: Various tiers based on usage needs
4. Fill in your details:
   - Email address
   - Organization name (individual or company)
   - Country
5. Verify your email address through the confirmation link

### Step 2: Access the Dashboard

1. After verification, log in to your account
2. Navigate to the **Dashboard** at https://apps.sentinel-hub.com/dashboard/
3. You'll see an overview of your account and available processing units

### Step 3: Create an OAuth Client

1. In the dashboard, go to **User Settings** (click your profile icon)
2. Select **OAuth clients** from the left sidebar
3. Click **"Create new OAuth client"**
4. Fill in the required fields:
   - **Name**: e.g., "JalDrishti Water Quality"
   - **Description**: "Water quality monitoring application"
   - **Type**: Select "CONFIDENTIAL" for server-side applications
5. Click **"Create"**

### Step 4: Generate Client Credentials

1. After creating the OAuth client, you'll see:
   - **Client ID**: A unique identifier for your application
   - **Client Secret**: A secret key (copy this immediately - it won't be shown again)
2. Save both the Client ID and Client Secret securely

### Step 5: Configure JalDrishti

1. Open the `.env` file in your JalDrishti project root
2. Add your Sentinel Hub OAuth credentials:

```env
SENTINEL_HUB_CLIENT_ID=your_client_id_here
SENTINEL_HUB_CLIENT_SECRET=your_client_secret_here
```

3. **Alternative**: If you have a direct Bearer token (not recommended), you can use:

```env
SENTINEL_HUB_API_KEY=your_bearer_token_here
```

**Note**: The backend now supports OAuth 2.0 authentication (Client ID + Secret) which is the recommended method. The system will automatically obtain and refresh access tokens as needed.

### Step 6: Test the Configuration

1. Restart your Flask backend:
```bash
cd backend
python app.py
```

2. Check the Sentinel-2 section in the frontend
3. The data source indicator should show "Live Sentinel-2 (Copernicus)" instead of "Synthetic"

## Pricing and Usage

### Free Trial (30 Days)
- **30,000 Processing Units (PU)** included
- Suitable for development and testing
- Automatic downgrade after trial period

### Paid Plans
- **Builder Plan**: €49/month - 100,000 PU/month
- **Explorer Plan**: €249/month - 500,000 PU/month
- **Professional Plan**: Custom pricing - Unlimited PU

### Processing Unit (PU) Cost
- **Sentinel-2 L2A**: ~1-3 PU per 1000 km² per band
- **Water Quality Indices**: ~4-12 PU per 1024×1024px request
- **India-wide (1024×1024px)**: ~8-16 PU per request

## Troubleshooting

### Issue: "401 Unauthorized" Error
- **Cause**: Invalid or expired API credentials
- **Solution**: 
  1. Verify Client ID and Secret are correct
  2. Regenerate Client Secret if needed
  3. Check if your trial period has expired

### Issue: "403 Forbidden" Error
- **Cause**: Insufficient permissions or quota exceeded
- **Solution**:
  1. Check your remaining PU balance in dashboard
  2. Upgrade your plan if needed
  3. Verify your OAuth client has correct scopes

### Issue: "429 Too Many Requests"
- **Cause**: Rate limit exceeded
- **Solution**:
  1. Implement request throttling in your application
  2. Cache responses to reduce API calls
  3. Upgrade to a higher tier plan

### Issue: "No Data Available" for Selected Date
- **Cause**: No cloud-free Sentinel-2 imagery available for the date
- **Solution**:
  1. Try a different date (within last 5 days)
  2. Adjust cloud cover filter (currently set to <30%)
  3. Check if the area is covered by Sentinel-2 orbit

## Alternative: Google Earth Engine

If Sentinel Hub is not suitable, consider using Google Earth Engine (GEE):

### GEE Setup
1. Visit https://earthengine.google.com/
2. Sign up with Google account
3. Request access (usually approved within 24-48 hours)
4. Use the Python API or JavaScript Code Editor

### GEE Advantages
- **Free for non-commercial use**
- **Large catalog of satellite data**
- **Built-in processing capabilities**
- **No API key required for basic usage**

### GEE Disadvantages
- **Requires JavaScript or Python coding**
- **No REST API for simple integration**
- **Rate limits apply**
- **Commercial use requires paid plan**

## Security Best Practices

1. **Never commit API keys to version control**
   - Add `.env` to `.gitignore`
   - Use environment variables in production

2. **Rotate credentials regularly**
   - Change Client Secret every 90 days
   - Revoke unused OAuth clients

3. **Use least privilege principle**
   - Create separate OAuth clients for different environments
   - Limit scopes to only what's needed

4. **Monitor usage**
   - Check dashboard regularly for unusual activity
   - Set up alerts for quota limits

## Support Resources

- **Sentinel Hub Documentation**: https://docs.sentinel-hub.com/
- **API Reference**: https://docs.sentinel-hub.com/api/latest/api/
- **Community Forum**: https://forum.sentinel-hub.com/
- **Support Email**: support@sentinel-hub.com

## Quick Reference

### API Endpoints Used in JalDrishti

- **Processing API**: `https://services.sentinel-hub.com/api/v1/process`
- **Catalog API**: `https://services.sentinel-hub.com/api/v1/catalog/1.0.0/`
- **Authentication**: OAuth 2.0 Bearer Token

### Evalscript Bands Used

- **B02**: Blue (490 nm) - CDOM, Kd490
- **B03**: Green (560 nm) - CDOM, Turbidity
- **B04**: Red (665 nm) - Turbidity, Chlorophyll-a
- **B05**: Red Edge (705 nm) - Chlorophyll-a
- **B08**: NIR (842 nm) - Turbidity correction
- **B11**: SWIR (1610 nm) - Depth correction for Kd490
- **SCL**: Scene Classification Layer - Cloud masking

### Data Collection

- **Sentinel-2 L2A**: Level-2A processed data (atmospherically corrected)
- **Cloud Cover**: <30% filter applied
- **Temporal Range**: Last 5 days by default
- **Spatial Resolution**: 10m (native), resampled to 1024×1024px for India

## Next Steps

After setting up your API key:

1. Test the Sentinel-2 section in JalDrishti
2. Verify spatial data loads correctly
3. Check that indices values are reasonable
4. Monitor your PU usage in the dashboard
5. Implement caching to reduce API calls
6. Consider scheduling updates (e.g., daily at 6 AM)

---

**Last Updated**: June 2026  
**JalDrishti Version**: 2.0  
**Sentinel Hub API Version**: v1
